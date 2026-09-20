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

## Real catalog and all discovered chapters

Subsequent real discovery on `https://zh.wikisource.org/wiki/西遊記` found 100
ordered chapter links, 第一回 through 第一百回, without a manually supplied list.
Project prj_a69af7789be04f959430db49eb4d8044, database:
/var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/nalu-public-catalog-0lh1vku2/db.

Session74182 fetched at most one new chapter per second, without automatic error
retries, and exited0: 100/100 complete, 741,632 extracted characters, no errors.
Recreated runtime over the saved database, with a reader that fails on any network
call: rediscovery and fetch-next reused the completed state without refetching.
Verified all 100 stored text SHA256 values. Sorted-key UTF-8 JSON URL/digest-list
manifest SHA256: facb4b86a7cc8f4b4bf2c7ee819a43a95af0911ceb0a995b403b991f1395068d.
`只改编第一百回` selected only the final chapter, 6,325 characters.

This proves this catalog's 100 chapters were imported and recovered. It does not
establish every site's compatibility, textual edition completeness, automated
search quality, successful model adaptation, video production or release.

The saved 741,632 characters were subsequently traversed with the actual
60,000-character writing-context budget and continuation cursors: 13 nonempty
windows. Concatenating all supplied passages equals the full stored text exactly;
SHA256 01c1c00ff302f4e02c7ffacc59eef4f47d1bdb7640159d2d41201d2390accfff.
No provider call or new network fetch was made for this coverage check.
