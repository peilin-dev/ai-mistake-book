# 合成文件样本

全部文件为本轮生成的虚构练习页，不包含学生信息。

- `sample-page.png`：800×1000 白底图片，写有一行示例算式。
- `sample-2pages.pdf`：两页 PDF，每页一条示例算式。
- `sample.zip`：包含 `IMG_2.png` 和应被忽略的 `__MACOSX/ignore.txt`。
- `sample-page.heic`：由同一张合成 PNG 转换的 HEIC。

浏览器检查：在独立 `/preview.html` 的“作业处理 → 上传卷子”选择这四个文件，预期得到 5 页，PDF 页码为 1、2，HEIC 和 ZIP 中的图片均能显示缩略图。预览不调用真实上传接口。
