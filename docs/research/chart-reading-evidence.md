# 圖表判讀的閱讀與研究依據

2026-11-20

讀一張陌生的圖，可以先問「圖上畫的是什麼？」「它想讓我比較什麼？」「看完這張圖，我實際能下什麼結論？」先確認尺度和分組，再讀出趨勢、差異或異常。最後回到圖面，檢查標題或標註引導的解讀是否有資料支持。這個順序是依下列來源整理的讀圖方法。 [Munzner 作者書頁](https://www.cs.ubc.ca/~tmm/vadbook/) · [Cairo 英文出版頁](https://wwnorton.co.uk/books/9781324001560-how-charts-lie)

## 從哪一本開始

1. **Alberto Cairo，《圖表會說謊》（*How Charts Lie*，2019）。** 適合從新聞、社群或簡報的讀者角度入門。書中以實例說明圖表的設計、不完整或不正確的資料，以及對圖樣的過度解讀如何改變印象。洪夏天譯本由商周出版，ISBN 9789864779222。 [英文出版頁](https://wwnorton.co.uk/books/9781324001560-how-charts-lie) · [繁中出版頁、目錄與試閱](https://www.cite.com.tw/book?id=86159)
2. **Tamara Munzner，*Visualization Analysis and Design*（2014）。** 從第 2、3、5 章開始。第 2 章用來辨認資料的項目和屬性，第 3 章用來明確提出讀圖任務，第 5 章用來拆解資料如何映射到位置、顏色、大小等視覺通道。可以用這三章建立可重複使用的讀圖詞彙。 [作者書頁與章節資源](https://www.cs.ubc.ca/~tmm/vadbook/)
3. **Cole Nussbaumer Knaflic，*Storytelling with Data*（2015）。** 第 1、2、4 章適合用來看懂簡報如何透過脈絡、圖型、顏色和標註引導注意。可先讀圖，再讀標題，看看兩次讀出的重點是否一致。這是從作者的溝通方法延伸出的練習。 [作者提供的初版章節與配套圖表](https://www.storytellingwithdata.com/book/downloads) · [作者書目](https://www.storytellingwithdata.com/books-1)

## 研究回答了哪些問題

| 讀圖問題 | 原始研究與適用範圍 |
| --- | --- |
| 哪種讀值比較精確？ | Cleveland 與 McGill（1984）讓受試者看指定的長條、堆疊長條和圓餅圖，估計較小值是較大值的百分之幾。這些實驗中，部分共同尺度的位置判讀比所比較的長度和角度更準確。論文也指出結果直接適用於實驗圖型和任務。Heer 與 Bostock（2010）以群眾實驗重做部分空間編碼研究，另研究矩形面積、圖尺寸與格線。從圖面估讀時，應讓文字精度與可見刻度相稱。 [Cleveland 與 McGill 原文，第 4 節](https://faculty.washington.edu/aragon/classes/hcde511/s12/readings/cleveland84.pdf) · [Heer 與 Bostock 論文](https://idl.uw.edu/papers/crowdsourcing-graphical-perception) |
| 可以練習哪些讀圖任務？ | Lee、Kim 與 Kwon（2017）的 VLAT 用 12 張圖、53 道選擇題涵蓋八類任務，包括讀值、找極值、比較與辨認趨勢或相關。這些題型可用來選擇練習內容。VLAT 的研究目的是評量人類視覺化素養。 [VLAT 原文](https://www.bckwon.com/pdf/vlat.pdf) |
| 如何檢查圖面會不會誤導？ | Ge、Cui 與 Kay（2023）的 CALVI 以 497 位受試者的試測資料發展批判讀圖評量。原文表 1 列出篩選資料、隱去不確定性、改變尺度範圍、標註誤導等做法。例如，若縱軸相同的間距代表不同幅度，應先讀刻度再比較斜率。每個檢查都要對應到當下要回答的問題。 [CALVI 原文，第 3 節與表 1](https://mucollective.northwestern.edu/files/2023-CALVI.pdf) |
| 可以用哪些題型驗證 AI？ | Masry 等人（2022）的 ChartQA 包含約 9,600 道人工撰寫問題和 23,100 道由人工圖表摘要生成的問題，用來測圖面辨識、邏輯與算術。Xu 等人的 ChartBench 加入許多未標示數值的圖，測試模型能否靠刻度、圖例與其他編碼讀值。兩者可以提供測試案例，ClipAI 的表現需要對實際使用的模型、提示詞和截圖另行測量。 [ChartQA 論文](https://aclanthology.org/2022.findings-acl.177/) · [ChartBench 論文](https://arxiv.org/abs/2312.15915) |

## 對 ClipAI 的應用

- **先建立圖面的比較條件。** 確認圖型、軸和單位、時間或樣本範圍、圖例及資料來源。只有當作答需要某個看不清的欄位，才提示使用者補上該部分。 [Munzner 作者書頁](https://www.cs.ubc.ca/~tmm/vadbook/) · [CALVI 原文](https://mucollective.northwestern.edu/files/2023-CALVI.pdf)
- **每個重點都能回到一處圖面。** 標明系列、時間或比較對象。有可讀標籤就引用標示值，從刻度推算就標「約」，缺少必要資訊時交代缺的是什麼。用估讀值計算差距時，也保留近似語氣。 [Cleveland 與 McGill 原文](https://faculty.washington.edu/aragon/classes/hcde511/s12/readings/cleveland84.pdf) · [ChartBench 論文](https://arxiv.org/abs/2312.15915)
- **把重要的判斷還給讀者。** 說明圖上關係，以及核實原因、代表性或下一步決策時還需要什麼證據。圖面有作者主張時，可引用主張，再指出哪些可見資料支持它。圖面有潛在誤導時，指出具體設計和它會改變哪個解讀。 [CALVI 原文](https://mucollective.northwestern.edu/files/2023-CALVI.pdf) · [ClipAI Human Space](../Product_philosophy.md#human-space)

首輪驗證可使用已知原始數值的圖，涵蓋有標值與無標值、模糊或裁切、尺度可能誤導，以及圖中沒有因果證據的情況。對照答案核對系列、單位、讀值、估值標示和結論依據，並記錄看不清時是否仍編出答案。這是根據上述題型推導的驗證方法，尚無 ClipAI 實測結果。
