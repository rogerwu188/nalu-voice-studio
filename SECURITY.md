# Security policy

## Reporting

Do not open a public issue for vulnerabilities involving credentials, paid API
submission, local file access, biometric media, child safety, or publishing.
Use GitHub's private vulnerability reporting for this repository.

Include affected version, reproduction steps, impact, and any suggested fix.
Please do not access data that is not yours or trigger paid generation while
testing.

## Supported versions

Until 1.0, only the latest tagged release receives security fixes.

## Security invariants

- The runtime binds to loopback by default.
- Biometric assets require explicit consent metadata.
- Child projects require guardian approval.
- Paid generation and publishing are separately approved actions.
- Secrets and personal media are excluded from source control.
- Imported historical scripts never override the product model policy.
