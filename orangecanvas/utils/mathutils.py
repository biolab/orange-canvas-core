def interp1d(start, end):
    memo = {}
    if (tuple(start), tuple(end)) in memo:
        return memo[(start, end)]

    diff = [e - s
            for e, s in zip(end, start)]

    r_start, r_end = 0, 1
    r_diff = r_end - r_start

    def interp(num):
        nonlocal memo

        if num in memo:
            return memo[num]
        percent = (num - r_start) / r_diff
        val = [s + d * percent
               for s, d in zip(start, diff)]
        memo[num] = val
        return val

    memo[(tuple(start), tuple(end))] = interp
    return interp
