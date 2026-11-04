# Device agent guide

This repository owns the Xiaomi 13 (fuxi, SM8550) board: DTS, peripheral wiring, component selection, firmware inputs,
the board probe and packaging. Shared SM8550 resources belong to `UniXNU-sm8550-common`; the build driver, the component
catalog and the documentation belong to UniXNU. This board builds with the fork
[OddlyLabs/UniXNU](https://github.com/OddlyLabs/UniXNU) (branch `fuxi`), whose catalog has the `FuxiFtsTouch`
component and whose `bootimg` takes the fuxi boot image options; upstream UniXNU has neither yet. The firmware is
[OddlyLabs/uefi-fuxi](https://github.com/OddlyLabs/uefi-fuxi) (branch `fuxi`): UniXNU/uefi-sheng with the fuxi commits of
matejkoo217/uefi-fuxi. Keep both forks as their upstream plus a small set of fuxi commits, merge upstream into them, and
update the pinned revisions in `.github/workflows/build.yml` after each merge.

## Read first

| Task | Required reading |
| --- | --- |
| Every change | [Porting](https://unixnu.com/porting/), [device repository](https://unixnu.com/porting/device-repository), the fork's `components.toml` |
| Hardware facts | `fuxi_touch_panel_porting.md` and `facts/` (every value names its source), the selected SoC DTSI |
| Touch | [FuxiFtsTouch](https://github.com/OddlyLabs/FuxiFtsTouch), `package/FuxiTouchProbe.cpp`, `package/FuxiTouchBoard.h` |
| Kernel | [Source and patches](https://unixnu.com/xnu/source-and-patches), `patches/xnu/series` |
| Images | [Prelink](https://unixnu.com/concepts/prelink), [payload](https://unixnu.com/concepts/payload), [UEFI](https://unixnu.com/porting/uefi-firmware) |

## Work

Take hardware values from the stock device tree or a measurement on the device, and record the source next to the value.
Other fuxi ports are references, not sources of truth. Do not copy GPL code (the Android `fts_spi` driver) into this
repository. `package/TouchBoard.h`, `package/QcomRpmh.*`, `package/SmmuBypass.h` and `package/ShengPlatformPower.cpp`
are unchanged copies from UniXNU-sheng `package/`, and `package/NativeHidInput.cpp` is an unchanged copy of UniXNU
ShengHidInput (71a40e7); keep them unchanged so they can be compared with their origin.

Run from the UniXNU fork checkout:

```sh
./unixnu defconfig fuxi_defconfig -D ../unixnu-fuxi
./unixnu status --json
./unixnu build kernel
python3 scripts/porting-record.py check --device ../unixnu-fuxi
```

Never flash the device. A test image is started with `fastboot boot` only, and only when the owner asks for it.

## Porting record

`porting.toml` is the shared record. Update the findings or evidence of each area whose files a change touches, and run
the record checker. Report host results and device observations separately, with the commit they were made at.
