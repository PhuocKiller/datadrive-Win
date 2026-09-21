/*
 * SPDX-FileCopyrightText: 2026 Tran Huy Phuoc
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "syncfoldershellstatus.h"

#include "config.h"
#include "configgui.h"

#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QLoggingCategory>
#include <QSettings>

#include <windows.h>

#include <aclapi.h>
#include <sddl.h>
#include <shlobj.h>

#include <memory>

namespace OCC
{

Q_LOGGING_CATEGORY(lcSyncFolderShellStatus, "nextcloud.gui.syncfoldershellstatus", QtInfoMsg)

namespace
{

constexpr auto shellClassInfoSection = "[.ShellClassInfo]";
constexpr auto iconResourceKey = "IconResource=";

// Used when the offline icon file is missing from the installation: the stock Windows error icon
// still tells the user that the folder is not connected.
constexpr auto fallbackOfflineIcon = "%SystemRoot%\\System32\\imageres.dll,-98";

QString executableIcon(const QString &index)
{
    return QDir::toNativeSeparators(QCoreApplication::applicationFilePath()) + QLatin1Char(',') + index;
}

void setNavigationPaneIcon(const QString &navigationPaneClsid, const QString &iconResource)
{
    if (navigationPaneClsid.isEmpty()) {
        return;
    }

    // Windows creates this key when it registers the sync root; a missing key means the entry is
    // already gone, and writing one here would conjure up an orphan.
    const auto clsidKey = QStringLiteral("HKEY_CURRENT_USER\\Software\\Classes\\CLSID\\") + navigationPaneClsid;
    if (!QSettings(clsidKey, QSettings::NativeFormat).childGroups().contains(QStringLiteral("DefaultIcon"))) {
        return;
    }

    QSettings defaultIcon(clsidKey + QStringLiteral("\\DefaultIcon"), QSettings::NativeFormat);
    defaultIcon.setValue(QStringLiteral("Default"), iconResource);
}

void setFolderIcon(const QString &folderPath, const QString &iconResource)
{
    const auto iniPath = QDir(folderPath).filePath(QStringLiteral("Desktop.ini"));
    const auto nativeIniPath = QDir::toNativeSeparators(iniPath).toStdWString();

    QByteArray content;
    QFile ini(iniPath);
    if (ini.exists()) {
        if (!ini.open(QIODevice::ReadOnly)) {
            qCWarning(lcSyncFolderShellStatus) << "Cannot read" << iniPath;
            return;
        }
        content = ini.readAll();
        ini.close();
        // UTF-16 is what Explorer writes when the user picks a custom icon; that choice wins.
        if (content.startsWith("\xFF\xFE") || content.startsWith("\xFE\xFF")) {
            return;
        }
    }

    QByteArrayList lines;
    auto hasSection = false;
    for (auto line : content.split('\n')) {
        line = line.trimmed();
        if (line.isEmpty() || line.startsWith(iconResourceKey)) {
            continue;
        }
        lines.append(line);
        if (line == shellClassInfoSection) {
            hasSection = true;
            lines.append(QByteArray(iconResourceKey) + iconResource.toUtf8());
        }
    }
    if (!hasSection) {
        lines.prepend(QByteArray(iconResourceKey) + iconResource.toUtf8());
        lines.prepend(shellClassInfoSection);
    }

    // A hidden system file refuses to be truncated in place, so drop those attributes first.
    SetFileAttributesW(nativeIniPath.c_str(), FILE_ATTRIBUTE_NORMAL);
    if (!ini.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        qCWarning(lcSyncFolderShellStatus) << "Cannot write" << iniPath;
        return;
    }
    ini.write(lines.join("\r\n") + "\r\n");
    ini.close();
    SetFileAttributesW(nativeIniPath.c_str(), FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM);

    // Explorer only reads Desktop.ini from folders marked as system or read-only; read-only on a
    // folder does not stop anything from being written into it.
    const auto nativeFolderPath = QDir::toNativeSeparators(folderPath).toStdWString();
    const auto folderAttributes = GetFileAttributesW(nativeFolderPath.c_str());
    if (folderAttributes != INVALID_FILE_ATTRIBUTES) {
        SetFileAttributesW(nativeFolderPath.c_str(), folderAttributes | FILE_ATTRIBUTE_READONLY);
    }
}

// SID of the user this process runs as; LocalFree releases it.
PSID currentUserSid()
{
    HANDLE token = nullptr;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) {
        return nullptr;
    }
    DWORD size = 0;
    GetTokenInformation(token, TokenUser, nullptr, 0, &size);
    std::unique_ptr<BYTE[]> buffer(new BYTE[size]);
    PSID copy = nullptr;
    if (GetTokenInformation(token, TokenUser, buffer.get(), size, &size)) {
        const auto user = reinterpret_cast<TOKEN_USER *>(buffer.get())->User.Sid;
        const auto length = GetLengthSid(user);
        copy = LocalAlloc(LMEM_FIXED, length);
        if (copy) {
            CopySid(length, copy, user);
        }
    }
    CloseHandle(token);
    return copy;
}

} // namespace

void SyncFolderShellStatus::setLocked(const QString &folderPath, bool locked)
{
    if (!QFileInfo(folderPath).isDir()) {
        return;
    }

    auto path = QDir::toNativeSeparators(folderPath).toStdWString();
    const auto sid = currentUserSid();
    if (!sid) {
        qCWarning(lcSyncFolderShellStatus) << "Cannot determine the current user to lock" << folderPath;
        return;
    }

    PACL dacl = nullptr;
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    if (GetNamedSecurityInfoW(path.data(), SE_FILE_OBJECT, DACL_SECURITY_INFORMATION, nullptr, nullptr, &dacl, nullptr, &descriptor) != ERROR_SUCCESS) {
        LocalFree(sid);
        qCWarning(lcSyncFolderShellStatus) << "Cannot read the permissions of" << folderPath;
        return;
    }

    // Look for the entry a previous lock left, so locking twice adds nothing and unlocking removes
    // exactly that one entry rather than every entry for the user.
    auto lockIndex = -1;
    ACL_SIZE_INFORMATION aclSize{};
    if (dacl && GetAclInformation(dacl, &aclSize, sizeof(aclSize), AclSizeInformation)) {
        for (DWORD index = 0; index < aclSize.AceCount; ++index) {
            void *entry = nullptr;
            if (!GetAce(dacl, index, &entry)) {
                continue;
            }
            const auto header = static_cast<ACE_HEADER *>(entry);
            if (header->AceType != ACCESS_DENIED_ACE_TYPE || (header->AceFlags & INHERITED_ACE)) {
                continue;
            }
            const auto denied = static_cast<ACCESS_DENIED_ACE *>(entry);
            if (denied->Mask == FILE_LIST_DIRECTORY && EqualSid(reinterpret_cast<PSID>(&denied->SidStart), sid)) {
                lockIndex = static_cast<int>(index);
                break;
            }
        }
    }

    PACL newDacl = nullptr;
    auto result = static_cast<DWORD>(ERROR_SUCCESS);
    if (locked && lockIndex < 0) {
        EXPLICIT_ACCESS_W denyListing{};
        denyListing.grfAccessPermissions = FILE_LIST_DIRECTORY;
        denyListing.grfAccessMode = DENY_ACCESS;
        denyListing.grfInheritance = NO_INHERITANCE;
        denyListing.Trustee.TrusteeForm = TRUSTEE_IS_SID;
        denyListing.Trustee.TrusteeType = TRUSTEE_IS_USER;
        denyListing.Trustee.ptstrName = static_cast<LPWSTR>(sid);
        result = SetEntriesInAclW(1, &denyListing, dacl, &newDacl);
        if (result == ERROR_SUCCESS) {
            result = SetNamedSecurityInfoW(path.data(), SE_FILE_OBJECT, DACL_SECURITY_INFORMATION, nullptr, nullptr, newDacl, nullptr);
        }
    } else if (!locked && lockIndex >= 0) {
        DeleteAce(dacl, static_cast<DWORD>(lockIndex));
        result = SetNamedSecurityInfoW(path.data(), SE_FILE_OBJECT, DACL_SECURITY_INFORMATION, nullptr, nullptr, dacl, nullptr);
    }

    if (result != ERROR_SUCCESS) {
        qCWarning(lcSyncFolderShellStatus) << "Cannot" << (locked ? "lock" : "unlock") << folderPath << "error" << result;
    } else if (locked != (lockIndex >= 0)) {
        qCInfo(lcSyncFolderShellStatus) << (locked ? "Locked" : "Unlocked") << folderPath;
    }

    if (newDacl) {
        LocalFree(newDacl);
    }
    LocalFree(descriptor);
    LocalFree(sid);
}

QString SyncFolderShellStatus::connectedFolderIcon()
{
#ifdef APPLICATION_FOLDER_ICON_INDEX
    return executableIcon(QStringLiteral(APPLICATION_FOLDER_ICON_INDEX));
#else
    return executableIcon(QStringLiteral("0"));
#endif
}

QString SyncFolderShellStatus::offlineIcon()
{
    const auto iconFile = QDir(QCoreApplication::applicationDirPath()).filePath(QStringLiteral(APPLICATION_EXECUTABLE "-offline.ico"));
    if (!QFileInfo::exists(iconFile)) {
        return QString::fromLatin1(fallbackOfflineIcon);
    }
    return QDir::toNativeSeparators(iconFile);
}

void SyncFolderShellStatus::apply(const QString &folderPath, const QString &navigationPaneClsid, bool connected)
{
    if (!QFileInfo(folderPath).isDir()) {
        return;
    }

    qCInfo(lcSyncFolderShellStatus) << "Marking" << folderPath << (connected ? "connected" : "offline") << "in Explorer";

    setNavigationPaneIcon(navigationPaneClsid, connected ? executableIcon(QStringLiteral("0")) : offlineIcon());
    setFolderIcon(folderPath, connected ? connectedFolderIcon() : offlineIcon());

    // Explorer caches icons per item; these ask it to redraw the folder and the navigation pane.
    const auto nativeFolderPath = QDir::toNativeSeparators(folderPath).toStdWString();
    SHChangeNotify(SHCNE_UPDATEITEM, SHCNF_PATHW | SHCNF_FLUSHNOWAIT, nativeFolderPath.c_str(), nullptr);
    SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST | SHCNF_FLUSHNOWAIT, nullptr, nullptr);
}

} // namespace OCC
