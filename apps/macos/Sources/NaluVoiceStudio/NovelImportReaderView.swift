import SwiftUI

struct NovelImportReaderView: View {
    let status: NovelImportStatus
    let chapterNumber: Int
    let chapter: NovelImportedChapter?
    let isLoading: Bool
    let error: String?
    let onRead: (Int) -> Void

    private var selected: NovelImportStatus.Chapter? {
        status.chapters.indices.contains(chapterNumber - 1) ? status.chapters[chapterNumber - 1] : nil
    }

    var body: some View {
        DisclosureGroup("已保存的小说原文（\(status.completed_chapters) / \(status.chapters.count) 章）") {
            VStack(alignment: .leading, spacing: 12) {
                Text("来源：\(status.source_url)")
                    .naluFont(.caption)
                    .textSelection(.enabled)
                    .foregroundStyle(.secondary)

                HStack(spacing: 12) {
                    Button("上一章") { onRead(chapterNumber - 1) }
                        .disabled(chapterNumber <= 1 || status.chapters.isEmpty)
                    Text("第 \(chapterNumber) 章，共 \(status.chapters.count) 章")
                        .naluFont(.headline)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel("第 \(chapterNumber) 章，共 \(status.chapters.count) 章")
                    Button("下一章") { onRead(chapterNumber + 1) }
                        .disabled(chapterNumber >= status.chapters.count)
                    Spacer(minLength: 8)
                    Button("打开这一章", systemImage: "book.pages") { onRead(chapterNumber) }
                        .buttonStyle(.borderedProminent)
                        .disabled(selected?.status != "complete" || isLoading)
                }

                if let selected {
                    Text(selected.title).naluFont(.title2, weight: .semibold)
                }
                if isLoading {
                    ProgressView("正在读取已保存的章节…")
                        .accessibilityElement(children: .combine)
                } else if let chapter, chapter.chapter_number == chapterNumber {
                    let visibleText = String(chapter.text.prefix(40_000))
                    Text(visibleText)
                        .naluFont(.body)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    if chapter.text.count > visibleText.count {
                        Text("本章较长，界面显示前 40,000 字；完整正文仍保存在项目中。")
                            .naluFont(.caption)
                            .foregroundStyle(.secondary)
                    }
                } else if let error {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .naluFont(.body)
                        .foregroundStyle(.orange)
                        .accessibilityIdentifier("nalu.novel-reader.error")
                } else if selected?.status != "complete" {
                    Text("这一章尚未完整保存，不能作为已读取正文。")
                        .naluFont(.body)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.top, 10)
        }
        .naluFont(.headline)
        .padding(18)
        .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 14))
        .accessibilityIdentifier("nalu.novel-reader")
    }
}
