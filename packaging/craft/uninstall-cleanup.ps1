# Dọn những gì DataDrive tự ghi ra lúc chạy. Bộ gỡ cài đặt của NSIS chỉ biết xoá thứ nó
# đã cài, nên nếu thiếu bước này thì Explorer vẫn còn mục DataDrive trỏ vào phần mềm đã biến mất.
#
# Thư mục đồng bộ ứng dụng tạo ra cũng bị xoá hẳn; dữ liệu trên server không bị đụng tới.
param([string]$InstallDir = "")

$ErrorActionPreference = "SilentlyContinue"

$appName = "DataDrive"
$configDir = Join-Path $env:APPDATA $appName
$configFile = Join-Path $configDir "datadrive.cfg"

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

# 2. Xoá hẳn các thư mục đồng bộ ứng dụng đã tạo.
#    Gỡ phần mềm nghĩa là thôi dùng dịch vụ trên máy này, nên thư mục đồng bộ cũng đi theo. Dữ
#    liệu trên server không bị đụng tới: ứng dụng đã bị gỡ, không còn gì để đẩy lệnh xoá lên. Chỉ
#    file sửa trên máy mà chưa kịp đồng bộ lúc gỡ là mất.
#
#    Chỉ xoá thư mục có dấu vết của ứng dụng: được ghi trong cấu hình, hoặc chứa journal
#    .sync_*.db. Thư mục riêng của người dùng tình cờ trùng tên thì không bị đụng.
$syncFolders = @()
if (Test-Path $configFile) {
    $syncFolders += Select-String -Path $configFile -Pattern '^\s*\S*localPath\s*=\s*(.+)$' |
        ForEach-Object { $_.Matches[0].Groups[1].Value.Trim().TrimEnd('/', '\') }
}
$syncFolders += Get-ChildItem $env:USERPROFILE -Directory -Force |
    Where-Object { $_.Name -like "$appName*" } |
    Where-Object { Get-ChildItem -LiteralPath $_.FullName -Force -Filter '.sync_*.db' } |
    ForEach-Object { $_.FullName }
$syncFolders = $syncFolders | Where-Object { $_ } | ForEach-Object { $_ -replace '/', '\' } | Sort-Object -Unique

foreach ($folder in $syncFolders) {
    if (-not (Test-Path -LiteralPath $folder)) { continue }

    # Ứng dụng chặn quyền liệt kê thư mục khi tài khoản đăng xuất. Chặn đó áp cho SID của người
    # dùng, mà tiến trình quản trị này cũng mang SID đó, nên phải trả quyền về mặc định trước.
    & icacls "$folder" /reset /q *> $null

    # Xoá cả cây thư mục một lượt thất bại với thư mục placeholder, nên xoá từng file trước rồi
    # các thư mục từ sâu ra ngoài.
    Get-ChildItem -LiteralPath $folder -Recurse -File -Force |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
    Get-ChildItem -LiteralPath $folder -Recurse -Directory -Force |
        Sort-Object { $_.FullName.Length } -Descending |
        ForEach-Object { & attrib -r -s -h "$($_.FullName)" 2>$null; try { [IO.Directory]::Delete($_.FullName) } catch {} }
    & attrib -r -s -h "$folder" 2>$null
    try { [IO.Directory]::Delete($folder) } catch {}
}

# Lối tắt tới thư mục đồng bộ mà ứng dụng thêm vào mục Links (Favorites) của Explorer.
Get-ChildItem (Join-Path $env:USERPROFILE 'Links') -Filter "$appName*.lnk" -Force |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }

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
