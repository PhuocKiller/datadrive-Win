# Dọn những gì DataDrive tự ghi ra lúc chạy. Bộ gỡ cài đặt của NSIS chỉ biết xoá thứ nó
# đã cài, nên nếu thiếu bước này thì Explorer vẫn còn mục DataDrive trỏ vào phần mềm đã biến mất.
#
# Về thư mục đồng bộ: file placeholder chỉ là con trỏ tới đám mây, chiếm 0 byte, và không thể
# mở được nữa một khi phần mềm hydrat hoá chúng đã bị gỡ. Xoá chúng không đụng tới dữ liệu trên
# server. File đã tải về thật thì giữ lại, vì đó mới là bản sao cục bộ duy nhất người dùng có.
param([string]$InstallDir = "")

$ErrorActionPreference = "SilentlyContinue"

$appName = "DataDrive"
$configDir = Join-Path $env:APPDATA $appName
$configFile = Join-Path $configDir "datadrive.cfg"

# FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | FILE_ATTRIBUTE_OFFLINE
$placeholderMask = 0x400000 -bor 0x1000

# 1. Gỡ đăng ký sync root. Đây mới là thứ giữ thư mục DataDrive trong khung điều hướng của
#    Explorer: Windows lưu nó ở HKLM, không phải HKCU. Gọi API Unregister trước để Windows tự
#    dọn đúng cách, rồi xoá khoá registry còn sót nếu API không làm được.
$syncRootKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\SyncRootManager"
$syncRootIds = Get-ChildItem $syncRootKey | Where-Object { $_.PSChildName -like "$appName!*" } |
    ForEach-Object { $_.PSChildName }
if ($syncRootIds) {
    $null = [Windows.Storage.Provider.StorageProviderSyncRootManager, Windows.Storage.Provider, ContentType = WindowsRuntime]
    foreach ($id in $syncRootIds) {
        [Windows.Storage.Provider.StorageProviderSyncRootManager]::Unregister($id)
        Remove-Item -LiteralPath (Join-Path $syncRootKey $id) -Recurse -Force
    }
}

# Tiến trình dllhost (COM surrogate) chạy shell extension của DataDrive giữ khoá trên các DLL
# trong thư mục cài đặt và mở database journal trong thư mục đồng bộ. Mọi bước xoá phía sau đều
# thất bại nếu nó còn sống, nên kết thúc nó trước. Đọc Modules của tiến trình hệ thống ném ngoại
# lệ Access denied, và ngoại lệ đó làm hỏng cả vòng lọc nếu không bắt lại.
function Stop-DataDriveSurrogates {
    Get-Process dllhost | Where-Object {
        try { $_.Modules.FileName -like "*\$appName\*" } catch { $false }
    } | Stop-Process -Force
    Start-Sleep -Seconds 2
}
Stop-DataDriveSurrogates

# 2. Dọn placeholder trong từng thư mục đồng bộ ghi trong cấu hình.
#    Thư mục mặc định luôn được xét, phòng khi cấu hình đã mất từ lần gỡ dở dang trước. An toàn vì
#    bước này chỉ xoá placeholder và sổ sách của ứng dụng, không bao giờ xoá file đã tải về.
$syncFolders = @(Join-Path $env:USERPROFILE $appName)
if (Test-Path $configFile) {
    $syncFolders += Select-String -Path $configFile -Pattern '^\s*localPath\s*=\s*(.+)$' |
        ForEach-Object { $_.Matches[0].Groups[1].Value.Trim().TrimEnd('/', '\') }
}
$syncFolders = $syncFolders | ForEach-Object { $_ -replace '/', '\' } | Sort-Object -Unique

if ($syncFolders) {
    foreach ($folder in $syncFolders) {
        if (-not (Test-Path -LiteralPath $folder)) { continue }

        Get-ChildItem -LiteralPath $folder -Recurse -File -Force |
            Where-Object { $_.Attributes -band $placeholderMask } |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }

        # Sổ sách của chính ứng dụng nằm lẫn trong thư mục người dùng: nhật ký đồng bộ, database
        # journal, và Desktop.ini mà ứng dụng ghi ra để đặt icon thư mục. Không phải tài liệu,
        # và vô dụng một khi ứng dụng đã bị gỡ.
        # Lọc theo tên thay vì -Include, vì -Include bị bỏ qua khi đi cùng -LiteralPath.
        $ownBookkeeping = @(".sync_*.db*", "._sync_*.db*", ".*sync.log", ".*permissions.log", "Desktop.ini")
        Get-ChildItem -LiteralPath $folder -Recurse -File -Force |
            Where-Object { $name = $_.Name; $ownBookkeeping | Where-Object { $name -like $_ } } |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }

        # Thư mục rỗng còn lại sau khi placeholder biến mất cũng không còn ý nghĩa gì.
        # Lặp vì xoá thư mục con có thể làm thư mục cha thành rỗng theo.
        for ($pass = 0; $pass -lt 8; $pass++) {
            $empty = Get-ChildItem -LiteralPath $folder -Recurse -Directory -Force |
                Where-Object { -not (Get-ChildItem -LiteralPath $_.FullName -Force) }
            if (-not $empty) { break }
            $empty | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
        }

        # Thư mục gốc chỉ xoá khi đã hoàn toàn trống, tức không còn file nào từng được tải về.
        & attrib -r -s -h "$folder" 2>$null
        if (-not (Get-ChildItem -LiteralPath $folder -Force)) {
            Remove-Item -LiteralPath $folder -Force
        }
    }
}

# 3. Cấu hình, cookie, và thư mục tạm ứng dụng tạo ra mỗi lần chạy.
Remove-Item -LiteralPath $configDir -Recurse -Force
Remove-Item -LiteralPath (Join-Path $env:LOCALAPPDATA $appName) -Recurse -Force
Get-ChildItem $env:TEMP -Force | Where-Object { $_.Name -like "$appName-*" } |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }

# 4. Shell extension và mục Explorer. CLSID của mục điều hướng do ứng dụng sinh ngẫu nhiên cho
#    mỗi thư mục đồng bộ, nên phải quét theo tên chứ không liệt kê cứng được.
$registryRoots = @(
    "HKCU:\SOFTWARE\Classes\CLSID",
    "HKCU:\SOFTWARE\Classes\AppID",
    "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Desktop\NameSpace"
)
foreach ($root in $registryRoots) {
    Get-ChildItem $root | ForEach-Object {
        $name = (Get-ItemProperty $_.PSPath).'(default)'
        if ($name -like "*$appName*") { Remove-Item -LiteralPath $_.PSPath -Recurse -Force }
    }
}

# 5. Mật khẩu trong Windows Credential Manager.
cmdkey /list | Select-String "Target:" | ForEach-Object {
    $target = ($_ -replace "^\s*Target:\s*", "").Trim() -replace "^LegacyGeneric:target=", ""
    if ($target -like "*$appName*") { cmdkey /delete:$target }
}

# 6. File chương trình còn sót. Phần lớn đã bị section chính của bộ gỡ xoá, nhưng các DLL shell
#    extension bị dllhost (COM surrogate) hoặc Explorer giữ nên xoá thất bại. Giờ đăng ký đã gỡ,
#    kết thúc tiến trình đang giữ chúng rồi xoá nốt.
if ($InstallDir -and (Test-Path -LiteralPath $InstallDir)) {
    # Explorer có thể gọi dllhost dậy lại ngay sau khi bị kết thúc, nên thử vài lượt.
    for ($attempt = 0; $attempt -lt 5 -and (Test-Path -LiteralPath $InstallDir); $attempt++) {
        Stop-DataDriveSurrogates
        Remove-Item -LiteralPath $InstallDir -Recurse -Force
    }

    # Explorer có thể vẫn nạp DLL overlay. Khởi động lại nó giải phóng khoá; dllhost có thể bị
    # Explorer gọi dậy lại trong lúc đó nên kết thúc lần nữa trước khi xoá.
    if (Test-Path -LiteralPath $InstallDir) {
        Stop-Process -Name explorer -Force
        Stop-DataDriveSurrogates
        Remove-Item -LiteralPath $InstallDir -Recurse -Force
        if (-not (Get-Process explorer)) { Start-Process explorer.exe }
    }
}
