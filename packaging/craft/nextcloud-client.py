# SPDX-License-Identifier: BSD-2-Clause
# SPDX-FileCopyrightText: 2021 Nextcloud GmbH and Nextcloud contributors

import os

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
            f'!define MUI_FINISHPAGE_RUN "{appExecutable}"',
            '!define MUI_FINISHPAGE_RUN_TEXT "Start DataDrive"',
        ])

        # Runs inside the install section, so the desktop shortcut lands next to the Start menu
        # one instead of leaving people to hunt for the app.
        self.defines["registry_hook"] = f'CreateShortCut "$DESKTOP\\DataDrive.lnk" "{appExecutable}"'

        # The uninstaller clears the Start menu folder on its own but knows nothing about the
        # desktop, so it would otherwise leave a shortcut to a file that is gone.
        self.defines["un_sections"] = "\n".join([
            "Section un.DesktopShortcut",
            '  Delete "$DESKTOP\\DataDrive.lnk"',
            "SectionEnd",
        ])

        self.ignoredPackages += ["binary/mysql"]
        if not CraftCore.compiler.isLinux:
            self.ignoredPackages += ["libs/dbus"]

        return super().createPackage()
