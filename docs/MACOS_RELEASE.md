# macOS build, signing and notarization

Nalu has two deliberately different release modes. A source builder can create an
ad-hoc-signed application for the same Mac without Apple credentials. A public release
candidate must use Developer ID, hardened runtime and Apple notarization. The application
and CI never describe an ad-hoc build as notarized.

## Local source build

Install full Xcode and Python 3.11 or newer, then run:

```bash
scripts/build-macos-release.sh
```

`NALU_PYTHON=/path/to/python` selects a particular interpreter. The build first validates
the actual Swift package manifest, so a mismatched Command Line Tools installation fails
before the slower Runtime bundle is assembled. The output is:

- `dist/Nalu Voice Studio.app`
- `dist/Nalu-Voice-Studio-macOS.zip`
- `dist/Nalu-Voice-Studio-macOS.zip.sha256`

Python is needed to build the application but is bundled into the app and is not required
on the end user's Mac.

## Developer ID release

Import a `Developer ID Application` certificate into the active keychain and create a
notarytool keychain profile. Then run:

```bash
NALU_RELEASE_VERSION=0.2.0 \
NALU_BUILD_NUMBER=20 \
NALU_SIGNING_IDENTITY='Developer ID Application: Example (TEAMID)' \
NALU_NOTARY_PROFILE='nalu-notary' \
NALU_REQUIRE_DEVELOPER_ID=true \
NALU_REQUIRE_NOTARIZATION=true \
scripts/build-macos-release.sh
```

The release process signs the embedded Runtime and native executable from the inside out,
signs the app with hardened runtime and the minimum audio/speech entitlements, submits the
zip to Apple, staples the ticket, validates Gatekeeper acceptance, rebuilds the final zip
and writes its SHA-256 file.

## GitHub release candidate workflow

The manually dispatched `macOS release candidate` workflow runs all Runtime and Swift
tests before building. A signed run fails closed unless all of these repository secrets
exist:

- `APPLE_DEVELOPER_ID_CERTIFICATE_BASE64`
- `APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD`
- `APPLE_SIGNING_IDENTITY`
- `APPLE_NOTARY_KEY_BASE64`
- `APPLE_NOTARY_KEY_ID`
- `APPLE_NOTARY_ISSUER_ID`

The workflow uploads the zip, checksum and a commit-bound provenance record. It does not
publish a GitHub Release, update users or send an application to a distribution platform.
Those remain separately authorized operations.
