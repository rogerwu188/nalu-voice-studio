import SwiftUI

struct ContentView: View {
    @Environment(VoiceInterviewViewModel.self) private var model

    var body: some View {
        HSplitView {
            sidebar.frame(minWidth: 260, idealWidth: 290, maxWidth: 340)
            interview
        }
        .task { await model.load() }
    }

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("Nalu 语音短剧工坊", systemImage: "waveform.circle.fill")
                .font(.title2.bold())
                .padding(.top, 22)
                .padding(.horizontal, 18)
            Text("我的短剧项目")
                .font(.headline)
                .padding(.horizontal, 18)
            List(model.projects) { project in
                VStack(alignment: .leading, spacing: 5) {
                    Text(project.title).font(.headline)
                    Text("计划 \(project.plannedEpisodeCount) 集")
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 5)
            }
            Button(action: beginProject) {
                Label("创建新项目", systemImage: "plus.circle.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding(18)
        }
    }

    private var interview: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading) {
                    Text("和 Nalu 讲故事").font(.title.bold())
                    Text(model.runtimeStatus).foregroundStyle(.secondary)
                }
                Spacer()
                Button("再说一遍", action: repeatQuestion).controlSize(.large)
            }
            .padding(24)
            Divider()
            ScrollView {
                LazyVStack(spacing: 18) {
                    ForEach(model.messages) { message in
                        bubble(message)
                    }
                }
                .padding(28)
            }
            if !model.transcript.isEmpty {
                Text(model.transcript)
                    .font(.title3)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding()
                    .background(Color.blue.opacity(0.08))
                    .padding(.horizontal, 24)
            }
            Button(action: toggleMicrophone) {
                Label(
                    model.isListening ? "说完了" : "按一下，然后开始说",
                    systemImage: model.isListening ? "stop.circle.fill" : "mic.circle.fill"
                )
                .font(.title2.bold())
                .frame(maxWidth: .infinity, minHeight: 58)
            }
            .buttonStyle(.borderedProminent)
            .tint(model.isListening ? .red : .blue)
            .padding(24)
        }
        .alert("Nalu 需要您的帮助", isPresented: errorBinding) {
            Button("知道了", role: .cancel) { model.errorMessage = nil }
        } message: {
            Text(model.errorMessage ?? "")
        }
    }

    private func bubble(_ message: InterviewMessage) -> some View {
        HStack(alignment: .top, spacing: 12) {
            if message.speaker == .user { Spacer(minLength: 80) }
            if message.speaker == .nalu {
                Image(systemName: "waveform.circle.fill")
                    .font(.title)
                    .foregroundStyle(.blue)
            }
            Text(message.text)
                .font(.title3)
                .lineSpacing(7)
                .padding(18)
                .background(bubbleColor(message), in: RoundedRectangle(cornerRadius: 18))
            if message.speaker == .nalu { Spacer(minLength: 80) }
        }
    }

    private func bubbleColor(_ message: InterviewMessage) -> Color {
        message.speaker == .nalu ? Color.blue.opacity(0.10) : Color.green.opacity(0.12)
    }

    private var errorBinding: Binding<Bool> {
        Binding(
            get: { model.errorMessage != nil },
            set: { if !$0 { model.errorMessage = nil } }
        )
    }

    private func beginProject() {
        model.messages = [
            InterviewMessage(
                speaker: .nalu,
                text: "我们来建立一个新项目。您想讲一个真实故事，还是创造一个全新的故事？"
            )
        ]
    }

    private func repeatQuestion() {
        model.messages.append(
            InterviewMessage(speaker: .nalu, text: "没关系，我们慢慢来。您想讲什么故事？")
        )
    }

    private func toggleMicrophone() {
        Task { await model.toggleListening() }
    }
}
