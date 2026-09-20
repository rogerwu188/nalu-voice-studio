# Actual public chapter reading

Implementation HEAD: 2c3d044. Source:
https://zh.wikisource.org/wiki/西遊記/第001回

- Installed isolated runtime18768 source-text GET succeeded: 7,550 characters,
  single_page_excerpt, truncated=false. This general reader includes navigation.
- Real NovelImport chapter reader (no mocked transport) saved 7,183 characters
  using reading_container extraction; import and chapter status complete.
- Body SHA256: e3345d3d54c1007ba8ac58aae1932d7cd9369bc7bd39d3ab9449d671eb75fc34.
- Separate local database:
  /var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/nalu-public-chapter-teyj06dx/db
- Project: prj_4382ec6694224ff7bf0b8f3ddc0f266a.
- Public interactive-story API accepted `只改编第一回，先整理第一集草稿`.
  Constructed writer request contains all 7,183 extracted characters with the
  same digest and requested_chapter_end=1.

The request was not sent to a provider. This proves one real, explicitly selected
chapter can be read, persisted and handed to writing context, not automatic book
discovery, entire-novel completeness, generated script quality or E2E release.
