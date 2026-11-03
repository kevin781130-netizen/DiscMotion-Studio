# DiscMotion Studio — CD-R 實體打樣前封板包

**雲端程式驗證 PASS；Windows 實機入口與 CD-R 光學效果均 NOT_RUN。** 只在 feature/zoetrope-animation-v1 開發；勿為實體測試合併 main。

## 一鍵準備 Windows 11 打樣檔案

需求：.NET 10 SDK、至少 2 GB 磁碟空間、12 張 00.png～11.png（可用 JPG/BMP/GIF 靜態來源）；不需 Docker 或 Python。從 GitHub 專案根目錄執行：

~~~powershell
.\tools\Zoetrope\Prepare-DeviceUAT.ps1 -Frames .\frames -OutDir .\device-uat
~~~

若系統阻止 ps1，先檢查 PowerShell 執行原則，不要永久放寬機器安全設定。

入口不會燒錄、不會覆蓋既有輸出；會生成 render/disc.png、render/preview.html、burn/disc-zoetrope.wav、burn/disc-zoetrope.cue、burn/disc-zoetrope.wav.json、PRE_DEVICE_REPORT.json。只有看到報告內 WINDOWS_ARTIFACT_PREP_PASS 才繼續；這仍不是實體打樣通過。Windows PowerShell 入口尚未在 Windows 實際跑過，狀態 NOT_RUN。封板雲端會以官方 PowerShell 7.6.9 執行語法解析及「來源不存在」拒絕測試（Linux 上執行），不代表 Windows 相容性通過。

## 已通過的雲端測試

- .NET10 Release 自測 / 12格 PNG：PASS
- CD-DA 原生編碼器 / WAV/CUE / 完整 359,849 扇區 (79:57.99)：PASS
- 高對比合成肖像的數位讀回，眨眼差異 0.5944、時序相關 0.9982：PASS
- 未校準的 216 條件退化模擬，158 條件保留數位眨眼：模型自測 PASS
- **以上只使用合成肖像，不能推論真實人像或物理 CD-R 成像。**
- WAV 的資料是視覺圖案的編碼載體，不是歌曲；不可宣稱可聽的音樂 CD。

## 第一次實體測試規範

1. **寫入**：使用規格相容的 80分鐘 CD-R 與光碟燒錄器；以支援 WAV+CUE 的 Audio-CD 燒錄模式寫入（DAO/SAO 若設備支援），不能把 WAV 複製成一般資料光碟。寫入速度依實際媒體與燒錄器支援範圍選，沒有通用保證速度。保留燒錄日誌與校驗結果。
2. **靜態**：記錄品牌、批次、燒錄器型號與韌體、燒錄速度；拍攝成品資料面、碟面方向、12 格分界、實際可見對比。如果無法辨認、燒錄失敗或方向相反，標 FAIL。
3. **動態**：僅在**有保護罩的穩定旋轉台**上由相機拍攝，絕不改裝光碟機、使用無遮罩外露旋轉裝置、照射眼睛或直接觀看強頻閃。理論 120 RPM × 12格 /60 =24格/秒，需要同步觀察/遮罩；**不是經驗證的最佳參數**。記錄 RPM、相機幀率、快門、照明與遮罩，以及連續 3 圈的檢查影片。
4. **判定**：完成寫入且安全受控錄影中，能連續 3 圈辨識正確的 12 格眨眼順序和方向，可記 PASS_DEVICE；任何硬體、方向、可視度、同步或安全問題為 FAIL_DEVICE；未嘗試一律 NOT_RUN。第一次只做可行性打樣，不算產品量產驗收。

## 封板與證據

- Render 發布的 pre-device-rc.json 是雲端證據匯總；physical 與 Windows 都須保留 NOT_RUN。
- 真正進行硬體驗收時，須保存 PRE_DEVICE_REPORT.json、燒錄紀錄、設備資訊、光碟照片與相機影片；不得用模擬畫面替代。
- **停止功能擴張。** 後續只有確認的 P0/P1 才允許在此分支修復，保留 SHA 和回歸證據。不上 main、不用 GitHub Actions。
