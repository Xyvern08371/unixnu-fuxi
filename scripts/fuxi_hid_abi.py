# SPDX-License-Identifier: BSD-2-Clause-Patent
"""The original IOHIDDevice that ShengHidInput's NativeHidInput derives from, in the iPadOS 17.7.11 kernelcache.

Shared by scripts/build-fuxi-hid-input.py (binds NativeHidInput's imports) and ci/check-hid-bindings.py (checks them in the
kernel that ships). The values are those UniXNU scripts/build-sheng-hid-input.py reads from its reference candidate; they
were read from the fuxi kernel of run 41419783238 and are the kernelcache's, so a kernel build does not move them.
"""

VPTR = 0xfffffff005d045c0                     # IOHIDDevice's vtable (the symbol __ZTV11IOHIDDevice is 16 bytes before)
SLOTS = 207                                   # an abstract device: 207 slots, slot 180 (newReportDescriptor) pure
BINDINGS = {'__ZN11IOHIDDeviceC2EPK11OSMetaClass': 0xfffffff004ad94f8, '__ZN11IOHIDDeviceD2Ev': 0xfffffff004ad9518,
            '__ZN11IOHIDDevice10gMetaClassE': 0xfffffff006ae6fa0, '__ZTV11IOHIDDevice': VPTR - 16}
# IOHIDDevice's own implementations by vtable slot: the 18 IOService slots it overrides and its slots 168 to 206.
KEXT_SLOTS = {
    0: 0xfffffff004ad951c, 1: 0xfffffff004ad9520, 7: 0xfffffff004ad9524, 12: 0xfffffff004b0b55c, 14: 0xfffffff004ad95fc,
    21: 0xfffffff004ad9590, 23: 0xfffffff004adced0, 76: 0xfffffff004adb0e4, 81: 0xfffffff004adaea4, 82: 0xfffffff004adaeb0,
    86: 0xfffffff004ad98ec, 87: 0xfffffff004adaebc, 91: 0xfffffff004adc3ac, 92: 0xfffffff004adc824, 93: 0xfffffff004adc93c,
    101: 0xfffffff004adb4cc, 132: 0xfffffff004adccb4, 140: 0xfffffff004adc978, 168: 0xfffffff004adc3a0,
    169: 0xfffffff004adc3a8, 170: 0xfffffff004adb680, 171: 0xfffffff004adcfdc, 172: 0xfffffff004adcfe4,
    173: 0xfffffff004adcfec, 174: 0xfffffff004adcff4, 175: 0xfffffff004adcffc, 176: 0xfffffff004add004,
    177: 0xfffffff004add00c, 178: 0xfffffff004add014, 179: 0xfffffff004add06c, 181: 0xfffffff004add0c4,
    182: 0xfffffff004add160, 183: 0xfffffff004add294, 184: 0xfffffff004addc54, 185: 0xfffffff004addc44,
    186: 0xfffffff004addc68, 187: 0xfffffff004addd74, 188: 0xfffffff004addea8, 189: 0xfffffff004addf34,
    190: 0xfffffff004addf50, 191: 0xfffffff004addf68, 192: 0xfffffff004ade02c, 193: 0xfffffff004ade184,
    194: 0xfffffff004ade1a4, 195: 0xfffffff004ade1c4, 196: 0xfffffff004ade1cc, 197: 0xfffffff004ade1d4,
    198: 0xfffffff004ade6d0, 199: 0xfffffff004ade75c, 200: 0xfffffff004add378, 201: 0xfffffff004ade890,
    202: 0xfffffff004adea2c, 203: 0xfffffff004adeb38, 204: 0xfffffff004adeca8, 205: 0xfffffff004adf42c,
    206: 0xfffffff004adf434}
OVERRIDES = [0, 1, 7, 12, 14, 21, 23, 76, 81, 82, 86, 87, 91, 92, 93, 101, 132, 140]
OWNED = [0, 1, 7, 14, 86, 87, 111, 171, 173, 180]   # NativeHidInput's own slots, as UniXNU's builder requires
# Instructions UniXNU's builder pins: the constructor with its vtable store, handleStart's calls of slots 168 and 180, and
# handleReport forwarding the timestamp, report, type and options.
CODE = {0xfffffff004ad94f8: 'fd7bbfa9fd0300912bd90094489100f008011791080000f9fd7bc1a8c0035fd6',
        0xfffffff004ad9aec: '680240f908a142f9e00313aae10314aa00013fd6680240f9603d003608d142f9e1630091e00313aa00013fd6a02d0035e00f40f9',
        0xfffffff004add110: '680240f9081543f9e00313aae20316aae30315aae40314aa00013fd6'}
