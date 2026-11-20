# site_model.py: when can the NEXT block's rest start after a pieced site of a prompt chunk, for four schedules of the site (a timeline model; parameters read off queue76's
# capture f76w with scripts/site_timeline.py, 4,096 rows, times in us a row and us an operation):
#   cur    today's: every fill, then every glue on the main stream, the shares after the exchanges on the side stream, the next block starts after the last share
#   il     the glue of piece q between the fills (after fill q + 1), so the side stream's order is x0 x1 s0 x2 s1 x3 s2 s3
#   pf     the next block's row-by-row front run per piece as each share lands, the glue as today (TF_GLM_OVN_PIECE_FFN's schedule)
#   sg     the pair's schedule: the glue on the side stream, order x_q g_q s_q a piece (the main stream only fills)
#   sg+pf  both (TF_GLM_OVN_PIECE_FRONT's and _MLA's schedule)
# The time printed is when the next block's rest (everything after its front) may start, from the first fill of this site; smaller is better. A model, not a measurement: it
# has no DRAM contention between the streams and takes every operation's time as a straight line in its rows.
import sys

R = 4096
PARAMS = {
    # this site: fill a, exchange bx, share bs, glue g (us a row); overhead per op (us); the next block's front fr (us a row: the MoE router 0.7 ms, the KDA projections 4.5, the DSA front 9)
    "mla->ffn": dict(a=0.87, bx=0.75, bs=0.30, g=0.36, of=15, ox=40, os=30, og=10, fr=0.17),
    "moe->kda": dict(a=1.30, bx=1.45, bs=0.30, g=0.36, of=15, ox=40, os=30, og=10, fr=1.10),
    "kda->ffn": dict(a=0.45, bx=0.75, bs=0.30, g=0.36, of=15, ox=40, os=30, og=10, fr=0.17),
    "moe->mla": dict(a=1.30, bx=1.45, bs=0.30, g=0.36, of=15, ox=40, os=30, og=10, fr=2.20),
}


def schedule(sizes, p, interleave, pieced_front, side_glue=False):
    n = len(sizes)
    main = 0.0
    E = []  # fill ends
    side = 0.0
    xe, se, ge = [0.0] * n, [0.0] * n, [0.0] * n
    queue = []  # the side stream's ops in issue order: ("x", q) or ("s", q)

    def run_x(q):
        nonlocal side
        s0 = max(side, E[q])
        side = s0 + p["bx"] * sizes[q] + p["ox"]
        xe[q] = side

    def run_s(q):
        nonlocal side
        s0 = max(side, ge[q])
        side = s0 + p["bs"] * sizes[q] + p["os"]
        se[q] = side

    def glue(q):
        nonlocal main
        main = max(main, xe[q]) + p["g"] * sizes[q] + p["og"]
        ge[q] = main

    if side_glue:
        # the pair's schedule: the main stream fills every piece; the side stream runs x_q, g_q, s_q for each piece in order
        for q in range(n):
            main += p["a"] * sizes[q] + p["of"]
            E.append(main)
        for q in range(n):
            s0 = max(side, E[q])
            side = s0 + p["bx"] * sizes[q] + p["ox"]
            xe[q] = side
            side += p["g"] * sizes[q] + p["og"]
            ge[q] = side
            side += p["bs"] * sizes[q] + p["os"]
            se[q] = side
    elif not interleave:
        for q in range(n):
            main += p["a"] * sizes[q] + p["of"]
            E.append(main)
            run_x(q)
        for q in range(n):
            glue(q)
            run_s(q)
    else:
        # program order: fill0, fill1, glue0, fill2, glue1, ..., fill n-1, glue n-2, glue n-1 (the side's ops follow in issue order)
        pending_s = []
        for q in range(n):
            main += p["a"] * sizes[q] + p["of"]
            E.append(main)
            run_x(q)
            if q >= 1:
                glue(q - 1)
                run_s(q - 1)
        glue(n - 1)
        run_s(n - 1)
    # the next site: its front per piece (waits that piece's share), then its rest after every front piece
    if not pieced_front:
        start = max(main, max(se))
        return start + p["fr"] * R
    t = main
    for q in range(n):
        t = max(t, se[q]) + p["fr"] * sizes[q] + 10
    return t


def main():
    global R
    cases = {
        4096: {"4 equal": (1024,) * 4, "tapered 4": (1152, 1152, 1024, 768), "6 equal-ish": (768, 768, 768, 768, 512, 512)},
        1326: {"4 pieces (a warm turn's 1,326 rows)": (384, 384, 384, 174), "6 pieces": (256,) * 5 + (46,)},
    }
    for rows, layouts in cases.items():
        R = rows
        print(f"#### {rows} rows")
        for name, p in PARAMS.items():
            print(f"== {name}")
            for lname, sizes in layouts.items():
                base = schedule(sizes, p, False, False)
                row = [f"{lname:36s} cur {base / 1000:.2f} ms"]
                for label, il, pf, sg in (("il", True, False, False), ("pf", False, True, False), ("sg", False, False, True), ("sg+pf", False, True, True)):
                    v = schedule(sizes, p, il, pf, sg)
                    row.append(f"{label} {v / 1000:.2f} ({(v - base) / 1000:+.2f} ms)")
                print("  " + "  ".join(row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
