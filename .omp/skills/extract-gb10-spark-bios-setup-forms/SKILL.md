---
name: extract-gb10-spark-bios-setup-forms
description: Extract the hidden UEFI Setup/IFR forms from a DGX Spark / ASUS GX10 (GB10) firmware capsule to inspect BIOS options or check for a power/TDP/overclock knob.
---

Use when asked to inspect the DGX Spark / GB10 BIOS Setup menu, find a power/TDP/GPU-clock/overclock knob, or extract the labeled Setup options. Applies to ASUS GX10, NVIDIA FE, and other GB10 vendors (they share the NVIDIA SoC FW).

## The trap (why a naive pass finds nothing)
The GB10 "BIOS" ships as an NVIDIA SoC-FW capsule in a non-standard container. UEFIExtract on the capsule finds only a ~436 KB standalone-MM FV and the main UEFI appears absent - because the **full UEFI DXE volume (with the Setup forms) is LZMA-compressed inside the capsule body**. A raw string scan therefore shows zero menu labels. Do not conclude "no Setup forms" from that; decompress first.

## Procedure
1. **Get the capsule (public, no login) from LVFS.** Fetch the catalog `https://cdn.fwupd.org/downloads/firmware.xml.xz` (xz -> ~18 MB XML), grep for the gx10 socfw entry, download its `.cab` (e.g. `bsp_ota2604_socfw307_bios_0105..._signed.cab`, ~29 MB). The cab payload is `socfw.cap`; `firmware.metainfo.xml` names the flashed GUID (f1392323-3920-4598-a932-ef06360cf403 = GX10 SoC FW) and version.
2. **Get the body.** `UEFIExtract socfw.cap` -> `socfw.cap.dump/body.bin` (strips the 32-byte EFI capsule header). GUID of the capsule wrapper is the standard FMP GUID 6DCBD5ED-E82D-4C44-BDA1-7194199AD92A.
3. **Find the hidden UEFI FV.** Scan `body.bin` for LZMA_ALONE streams: byte pattern `5d 00 00`, then validate the 13-byte header (props==0x5d, dict size 2^12..2^28, uncompressed size often 0xFFFFFFFFFFFFFFFF = streaming). Decompress each candidate with Python `lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)`. The main UEFI is the stream that yields a multi-MB blob containing `_FVH` (at offset ~40) and UTF-16 Setup strings (Security/Advanced/Boot). For socfw v3.0.7 it was at body offset `0xdd7de1` -> 32 MB FV, but the offset is version-specific: decompress all candidates and pick by `_FVH` + Setup strings.
4. **Decode the forms.** `UEFIExtract uefi_main.fv` then IFRExtractor-RS (github LongSoft/IFRExtractor-RS release binary): `ifrextractor uefi_main.fv all` -> `*.ifr.txt` (one per form×string-package cross-product; most pairings have mismatched strings, find coherent ones by sensible FormSet titles like "Advanced Menu"/"NVIDIA").
5. **Enumerate options.** Opcodes are `OneOf Prompt: "..."`, `Numeric Prompt: "..."`, `CheckBox Prompt: "..."` (note no space in `OneOf`). Grep all files and dedupe. The real Setup varstore is `Setup`, GUID EC87D643-EBA4-4BB5-A1E5-3F3E36B20DA9, size 0x51 (81 bytes) - matches the live EFI variable, and is writable from Linux as root even when a menu is suppressed/`GrayOutIf True`.

## Known result (socfw 3.0.7, Oct 2026)
Full AMI Aptio Setup exists (Main/Advanced/Chipset/Security/Boot/Save&Exit + NVIDIA Platform Config + NVMe/Network/TPM) but is mostly suppressed in shipping firmware (users see only 2 boot entries). **No TDP / power-limit / GPU-clock / overclock / turbo / wattage option exists anywhere.** Only platform tunables: iGPU Memory Carveout, Available System Memory (SoC split), DLA Support, C2C, DRAM validation (Eyescan/RAPID-K/Voltage) - plus power-*saving* items (PCIe ASPM/L1SS, ACPI sleep). NVIDIA Platform Config is grayed out + dynamically generated. The ~140 W GPU envelope is set by signed PD(5.22)+GSP firmware, not the BIOS.

## The "recovery image" is not a richer BIOS
`ASUS-Ascent-GX10-OS-7.5.0-2.zip` (9.24 GB) is a `.tar.gz` of the DGX OS, bundling the same signed capsules - not a fuller BIOS. Direct (open CDN): `https://dlcdnets.asus.com/pub/ASUS/Desktop/Vivo_PC/GX10/ASUS-Ascent-GX10-OS-7.5.0-2-20260525090919.zip` (Accept-Ranges: bytes; read the ZIP central directory via a range request to list contents without downloading 9 GB). Extract the BIOS from the capsule, not this.

## Tools on this box
UEFIExtract: `work/uefitool_win/UEFIExtract.exe` (run via full path; relative `./` exec is blocked). IFRExtractor-RS: download the Windows release zip, run via full path. Windows `python3` has `lzma`. HTTP range reads: Bun `fetch` with a `Range` header from the eval js kernel works with no CORS.
