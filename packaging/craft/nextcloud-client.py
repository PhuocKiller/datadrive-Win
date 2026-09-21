# SPDX-License-Identifier: BSD-2-Clause
# SPDX-FileCopyrightText: 2021 Nextcloud GmbH and Nextcloud contributors

import os
from pathlib import Path

import info
from Package.CMakePackageBase import *

class subinfo(info.infoclass):
    def registerOptions(self):
        self.options.dynamic.registerOption("devMode", False)
        self.options.dynamic.registerOption("versionSuffix", "")
        self.options.dynamic.registerOption("buildWithWebEngine", True)
        if CraftCore.compiler.isMacOS:
            self.options.dynamic.registerOption("osxArchs", "arm64")
            self.options.dynamic.registerOption("buildMacOSBundle", True)
            self.options.dynamic.registerOption("buildFileProviderModule", False)
            self.options.dynamic.registerOption("sparkleLibPath", "")
            self.options.dynamic.registerOption("overrideServerUrl", "")
            self.options.dynamic.registerOption("forceOverrideServerUrl", False)

    def setTargets(self):
        self.svnTargets["master"] = "[git]https://github.com/nextcloud/desktop"

        self.description = "DataDrive Desktop Client"
        self.displayName = "DataDrive"
        self.webpage = "https://datadrive.vn"

        self.defaultTarget = "master"

    def setDependencies(self):
        self.buildDependencies["dev-utils/cmake"] = None
        self.runtimeDependencies["libs/qt6/qtbase"] = None
        self.runtimeDependencies["libs/qt6/qtdeclarative"] = None

        if self.options.dynamic.buildWithWebEngine:
            self.runtimeDependencies["libs/qt6/qtwebengine"] = None

        self.runtimeDependencies["libs/qt6/qtwebsockets"] = None
        self.runtimeDependencies["libs/qt/qtsvg"] = None
        self.runtimeDependencies["libs/qt6/qt5compat"] = None
        self.runtimeDependencies["libs/zlib"] = None
        self.runtimeDependencies["libs/libp11"] = None
        self.runtimeDependencies["libs/kdsingleapplication"] = None
        self.runtimeDependencies["qt-libs/qtkeychain"] = None
        self.runtimeDependencies["kde/frameworks/tier1/karchive"] = None
        if CraftCore.compiler.isLinux:
            self.runtimeDependencies["kde/frameworks/tier1/kdbusaddons"] = None

        self.runtimeDependencies["libs/openssl"] = None

class Package(CMakePackageBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        def boolToCmakeBool(value: bool) -> str:
            return "ON" if value else "OFF"

        devMode = self.subinfo.options.dynamic.devMode
        versionSuffix = self.subinfo.options.dynamic.versionSuffix
        overrideServerUrl = self.subinfo.options.dynamic.overrideServerUrl

        # Make sure we do not set the application server url to empty if it is not set, this can
        # unintentionally break our use of NEXTCLOUD.cmake
        if overrideServerUrl:
            forceOverrideServerUrl = "ON" if self.subinfo.options.dynamic.forceOverrideServerUrl == True else "OFF"
            self.subinfo.options.configure.args += [
                f"-DAPPLICATION_SERVER_URL={overrideServerUrl}",
                f"-DAPPLICATION_SERVER_URL_ENFORCE={forceOverrideServerUrl}"
            ]

        if devMode:
            self.subinfo.options.configure.args += [f"-DNEXTCLOUD_DEV=ON"]

        self.subinfo.options.configure.args += [f"-DMIRALL_VERSION_SUFFIX={versionSuffix}"]

        buildWithWebEngine = boolToCmakeBool(self.subinfo.options.dynamic.buildWithWebEngine)
        self.subinfo.options.configure.args += [f"-DBUILD_WITH_WEBENGINE={buildWithWebEngine}"]

        if CraftCore.compiler.isMacOS:
            osxArchs = self.subinfo.options.dynamic.osxArchs
            buildAppBundle = boolToCmakeBool(self.subinfo.options.dynamic.buildMacOSBundle)
            buildFileProviderModule = boolToCmakeBool(self.subinfo.options.dynamic.buildFileProviderModule)
            sparkleLibPath = self.subinfo.options.dynamic.sparkleLibPath
            self.subinfo.options.configure.args += [
                f"-DCMAKE_OSX_ARCHITECTURES={osxArchs}",
                f"-DBUILD_OWNCLOUD_OSX_BUNDLE={buildAppBundle}",
                f"-DBUILD_FILE_PROVIDER_MODULE={buildFileProviderModule}",
                f"-DSPARKLE_LIBRARY={sparkleLibPath}",
            ]

    def createPackage(self):
        self.blacklist_file.append(os.path.join(self.packageDir(), 'blacklist.txt'))
        self.defines["appname"] = "datadrive"
        self.defines["company"] = "Tran Huy Phuoc"
        self.applicationExecutable = "datadrive"
        # Craft khong con doc thuoc tinh applicationExecutable o tren. NullsoftInstallerPackager
        # sinh khoi shortcut tu defines["executable"], duong dan tuong doi so voi $INSTDIR.
        # Thieu dong nay thi bo cai khong tao shortcut Start Menu nao.
        self.defines["executable"] = "bin/datadrive.exe"

        # PackagerBase falls back to craft.ico, which is why an unbranded installer shows the
        # craft logo and drops craft.ico into the install directory.
        installerIcon = os.path.join(self.sourceDir(), "admin", "win", "nsi", "installer.ico")
        if os.path.isfile(installerIcon):
            self.defines["icon"] = installerIcon

        # For a git target PackagerBase uses the checked-out revision, so the installer ends up
        # calling its version "master" or, on a work branch, something worse.
        self.defines["version"] = "1.0.0"

        appExecutable = r"$INSTDIR\bin\datadrive.exe"

        # The template defines this placeholder ahead of MUI_PAGE_FINISH, which is where
        # MUI_FINISHPAGE_RUN has to be set for the finish page to offer to start the app.
        self.defines["sections_page"] = "\n".join([
            # A plain MUI_FINISHPAGE_RUN starts the client with the installer's administrator
            # token. A sync client running elevated is cut off from the user's non-elevated
            # Explorer and windows by UIPI, and writes into the sync folder as administrator.
            # The function hands the launch to Explorer, which starts it as the logged-in user.
            "!define MUI_FINISHPAGE_RUN",
            '!define MUI_FINISHPAGE_RUN_TEXT "Start DataDrive"',
            "!define MUI_FINISHPAGE_RUN_FUNCTION LaunchDataDriveAsUser",
        ])

        # The desktop shortcut has to be created after the payload is unpacked. registry_hook runs
        # before the 7za extraction, and a shortcut made then points at a datadrive.exe that does
        # not exist yet, so Windows caches a blank icon for it until something later forces a
        # refresh. The template's only top-level hook after extraction that does not also switch
        # on a components page is un_sections, so the install section goes in there; NSIS runs
        # plain sections in the order they appear, whatever comes around them.
        desktopShortcutSection = [
            "Function LaunchDataDriveAsUser",
            f'  Exec \'"$WINDIR\\explorer.exe" "{appExecutable}"\'',
            "FunctionEnd",
            "",
            "Section",
            f'  CreateShortCut "$DESKTOP\\DataDrive.lnk" "{appExecutable}" "" "{appExecutable}" 0',
            # SHCNE_ASSOCCHANGED: tells Explorer to drop cached icons and redraw the desktop now.
            "  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'",
            "SectionEnd",
            "",
        ]

        # Everything the running app leaves behind that the stock uninstaller never touches.
        #
        # The uninstaller clears the Start menu folder and the files it installed, and nothing
        # else. The app registers its shell extensions and its Explorer entry under HKCU while
        # it runs, and writes its configuration and its password into the user profile, so
        # uninstalling without this leaves a DataDrive entry sitting in Explorer pointing at
        # software that is gone.
        #
        # The synchronised folder itself is deliberately left alone: those are the user's own
        # documents, and no uninstaller should delete documents.
        # The Explorer entry uses a CLSID that folder.cpp draws from QUuid::createUuid() per sync
        # folder, so no fixed list can cover it. The cleanup sweeps HKCU for keys the app named
        # after itself instead, and clears its saved password the same way.
        #
        # The uninstaller writes the script to a temporary file and runs it from there. Passing it
        # inline is not an option: an NSIS string holds 1024 characters, and the script is longer
        # than that however it is encoded. Installing it alongside the program would not work
        # either, because the section that deletes the program files runs before this one.
        cleanupLines = (Path(__file__).parent / "uninstall-cleanup.ps1").read_text(encoding="utf-8").splitlines()

        def toNsisString(line: str) -> str:
            return line.replace("$", "$$").replace('"', '$\\"').replace("`", "$\\`")

        unSections = desktopShortcutSection + [
            "Section un.DesktopShortcut",
            '  Delete "$DESKTOP\\DataDrive.lnk"',
            "SectionEnd",
            "",
            "Section un.UserState",
            '  StrCpy $1 "$TEMP\\datadrive-uninstall-cleanup.ps1"',
            # The error flag is sticky in NSIS. The main uninstall section sets it whenever a
            # locked shell extension DLL refuses to go, and without clearing it here IfErrors
            # below would skip every FileWrite and leave an empty script behind.
            "  ClearErrors",
            '  FileOpen $0 "$1" w',
            "  IfErrors cleanupDone",
        ]
        for line in cleanupLines:
            unSections.append(f'  FileWrite $0 "{toNsisString(line)}$\\r$\\n"')
        unSections += [
            "  FileClose $0",
            '  nsExec::ExecToLog \'powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$1" -InstallDir "$INSTDIR"\'',
            "  Pop $2",
            '  Delete "$1"',
            "  cleanupDone:",
            "SectionEnd",
        ]
        self.defines["un_sections"] = "\n".join(unSections)

        self.ignoredPackages += ["binary/mysql"]
        if not CraftCore.compiler.isLinux:
            self.ignoredPackages += ["libs/dbus"]

        return super().createPackage()
