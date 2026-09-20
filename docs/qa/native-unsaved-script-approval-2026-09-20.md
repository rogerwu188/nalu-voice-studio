# Installed native script approval snapshot QA

Artifact: CI35533755125, arm64 artifact10612362650, product7721e44.
ZIP SHA-256: be3f57110ddb3a2cfca9606c9865a3cc366ff48f1400eb3522db5ef11c794ebf,
matches the accompanying CI checksum (its filename includes the CI dist prefix).
Installed at /tmp/nalu-approval-qa-I2ww4m/app/Nalu Voice Studio.app.
Isolated support: /var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/nalu-native-story-fg8o7f5k.
Runtime port18772; launch-only writer endpoint invalid-local-qa; no paid calls.
Project prj_14ed95d15e6c4ee6b71e122bafdbd69f; first episode
ep_63ee0ac3533646d49bce58e50f9c7bbe. Narrated-source synthetic fixture.

Observed via native accessibility UI:

1. Typed and sent `采用第一集草稿`; first episode entered script_review15%,
   explicitly not approved or paid. Second episode stayed planned0%.
2. Expanded script editor. Changed body to
   `【合成 QA 未保存修改】小夏和爷爷一起回家。` without saving.
3. Clicked `批准当前剧本`. Alert required saving and reviewing latest body/summary;
   after dismissal the exact edited body remained and progress stayed15%.
4. Changed summary to `【合成 QA】小夏与爷爷回家。`; saved new version.
   Version1 and version2 buttons were both present.
5. Clicked approve. Version2 became `已批准`, progress20%/script_approved,
   planning locked; UI stated ready for production preparation. No production
   was started, and no voice recognition, real writer or media QA is claimed.

This closes this installed editor-guard scenario only, not SOP04 or the full
release candidate. Current source HEAD includes later campaign changes absent
from this artifact. Native restart after this approval remains untested here.
