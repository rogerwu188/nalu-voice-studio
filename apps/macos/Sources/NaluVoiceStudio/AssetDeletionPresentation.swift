import Foundation

extension AssetDependencyReport {
    var allowsDeletionPresentation: Bool {
        canDelete && productionRunIDs.isEmpty
    }

    var deletionMessage: String {
        if allowsDeletionPresentation {
            return "这份素材尚未被制作快照引用。删除会移除 Nalu 保存的本地副本；原始文件不受影响。现在还没有删除，您可以点“取消”保留素材。"
        }
        if !productionRunIDs.isEmpty {
            return "这份素材已被 \(productionRunIDs.count) 个制作快照使用，暂时不能删除，以免影响已有作品。素材已保留，点“取消”返回。"
        }
        return "目前不能安全删除这份素材。素材已保留，请返回后重新检查。"
    }
}
