#!/usr/bin/env bash
# Decrypt the image artifact of the Build workflow on the machine that holds the private key.
#
# The workflow encrypts boot.img, and the unpatched prelinked kernel (kernel.macho.gz) when the artifact has it, with one
# random key (AES-256-CBC, PBKDF2) and that key with ci/boot-image-recipient.pem (RSA-OAEP, SHA-256): both are built from
# Apple's kernelcache and are not published. The private key never leaves the owner's machine.
#
# usage: ci/decrypt-boot-image.sh <private key PEM> <artifact directory> [output boot.img]
# The kernel, when present, is written as kernel.macho next to the output image.
set -euo pipefail
key=$1
dir=$2
out=${3:-$dir/boot.img}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp "$dir/boot.img.enc" "$dir/boot.key.enc" "$work/"
[ -f "$dir/kernel.macho.gz.enc" ] && cp "$dir/kernel.macho.gz.enc" "$work/"
cp "$key" "$work/private.pem"
(
  cd "$work"   # relative paths: a native openssl.exe on Windows reads them as they are
  openssl pkeyutl -decrypt -inkey private.pem -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256 \
    -in boot.key.enc -out boot.key
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in boot.img.enc -out boot.img -pass file:boot.key
  if [ -f kernel.macho.gz.enc ]; then
    openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in kernel.macho.gz.enc -out kernel.macho.gz -pass file:boot.key
  fi
)
check() {   # file, sha256 list
  local want got
  want=$(cut -d' ' -f1 "$2")
  got=$(sha256sum "$1" | cut -d' ' -f1)
  [ "$want" = "$got" ] || { echo "sha256 mismatch for $1: $got, expected $want" >&2; exit 1; }
}
check "$work/boot.img" "$dir/boot.img.sha256"
mv "$work/boot.img" "$out"
echo "decrypted $out (sha256 $(cut -d' ' -f1 "$dir/boot.img.sha256"))"
if [ -f "$work/kernel.macho.gz" ]; then
  check "$work/kernel.macho.gz" "$dir/kernel.macho.gz.sha256"
  kernel=$(dirname "$out")/kernel.macho
  gzip -d -c "$work/kernel.macho.gz" > "$kernel"
  echo "decrypted $kernel (sha256 $(sha256sum "$kernel" | cut -d' ' -f1))"
fi
