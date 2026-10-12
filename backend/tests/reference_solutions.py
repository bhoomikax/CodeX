"""Reference solutions for the console-I/O contracts in data/test_cases.json.

Each function takes the raw stdin text and returns the expected stdout text.
They exist so the test suite can independently confirm every hand-written
expected output in the seed data. They are never executed on learner code.
"""
import heapq
from collections import Counter, deque


def _lines(text):
    return text.replace("\r\n", "\n").split("\n")


def _ints(line):
    return [int(x) for x in line.split()] if line.strip() else []


def _bool(value):
    return "true\n" if value else "false\n"


def _join(values):
    return " ".join(str(v) for v in values) + "\n"


def _array_and_rest(text):
    """Line 1: n. Line 2: n integers. Remaining lines returned as-is."""
    lines = _lines(text)
    n = int(lines[0])
    nums = _ints(lines[1]) if len(lines) > 1 else []
    assert len(nums) == n, f"declared {n} values, found {len(nums)}"
    return nums, lines[2:]


def two_sum_ii(text):  # 167
    nums, rest = _array_and_rest(text)
    target = int(rest[0])
    left, right = 0, len(nums) - 1
    while left < right:
        total = nums[left] + nums[right]
        if total == target:
            return f"{left + 1} {right + 1}\n"
        if total < target:
            left += 1
        else:
            right -= 1
    raise AssertionError("no solution")


def valid_palindrome(text):  # 125
    s = _lines(text)[0]
    cleaned = [c.lower() for c in s if c.isalnum()]
    return _bool(cleaned == cleaned[::-1])


def remove_duplicates(text):  # 26
    nums, _ = _array_and_rest(text)
    k = 0
    for value in nums:
        if k == 0 or nums[k - 1] != value:
            nums[k] = value
            k += 1
    return f"{k}\n" + _join(nums[:k])


def max_average_subarray(text):  # 643
    nums, rest = _array_and_rest(text)
    k = int(rest[0])
    window = sum(nums[:k])
    best = window
    for i in range(k, len(nums)):
        window += nums[i] - nums[i - k]
        best = max(best, window)
    return f"{best / k:.5f}\n"


def longest_unique_substring(text):  # 3
    s = _lines(text)[0]
    seen = {}
    start = best = 0
    for i, c in enumerate(s):
        if c in seen and seen[c] >= start:
            start = seen[c] + 1
        seen[c] = i
        best = max(best, i - start + 1)
    return f"{best}\n"


def contains_duplicate(text):  # 217
    nums, _ = _array_and_rest(text)
    return _bool(len(set(nums)) != len(nums))


def valid_anagram(text):  # 242
    s, t = _lines(text)[:2]
    return _bool(Counter(s) == Counter(t))


def valid_parentheses(text):  # 20
    s = _lines(text)[0]
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    for c in s:
        if c in pairs:
            if not stack or stack.pop() != pairs[c]:
                return _bool(False)
        else:
            stack.append(c)
    return _bool(not stack)


def best_time_to_buy_and_sell(text):  # 121
    prices, _ = _array_and_rest(text)
    low, best = float("inf"), 0
    for p in prices:
        low = min(low, p)
        best = max(best, p - low)
    return f"{best}\n"


def climbing_stairs(text):  # 70
    n = int(_lines(text)[0])
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return f"{a}\n"


def house_robber(text):  # 198
    nums, _ = _array_and_rest(text)
    rob = skip = 0
    for value in nums:
        rob, skip = skip + value, max(rob, skip)
    return f"{max(rob, skip)}\n"


def coin_change(text):  # 322
    coins, rest = _array_and_rest(text)
    amount = int(rest[0])
    dp = [0] + [float("inf")] * amount
    for a in range(1, amount + 1):
        for c in coins:
            if c <= a and dp[a - c] + 1 < dp[a]:
                dp[a] = dp[a - c] + 1
    return f"{dp[amount] if dp[amount] != float('inf') else -1}\n"


def last_stone_weight(text):  # 1046
    stones, _ = _array_and_rest(text)
    heap = [-s for s in stones]
    heapq.heapify(heap)
    while len(heap) > 1:
        a, b = -heapq.heappop(heap), -heapq.heappop(heap)
        if a != b:
            heapq.heappush(heap, -(a - b))
    return f"{-heap[0] if heap else 0}\n"


def jump_game(text):  # 55
    nums, _ = _array_and_rest(text)
    reach = 0
    for i, step in enumerate(nums):
        if i > reach:
            return _bool(False)
        reach = max(reach, i + step)
    return _bool(True)


def min_size_subarray_sum(text):  # 209
    nums, rest = _array_and_rest(text)
    target = int(rest[0])
    best, total, left = float("inf"), 0, 0
    for right, value in enumerate(nums):
        total += value
        while total >= target:
            best = min(best, right - left + 1)
            total -= nums[left]
            left += 1
    return f"{0 if best == float('inf') else best}\n"


def daily_temperatures(text):  # 739
    temps, _ = _array_and_rest(text)
    answer = [0] * len(temps)
    stack = []
    for i, t in enumerate(temps):
        while stack and temps[stack[-1]] < t:
            j = stack.pop()
            answer[j] = i - j
        stack.append(i)
    return _join(answer)


def product_except_self(text):  # 238
    nums, _ = _array_and_rest(text)
    n = len(nums)
    out = [1] * n
    prefix = 1
    for i in range(n):
        out[i] = prefix
        prefix *= nums[i]
    suffix = 1
    for i in range(n - 1, -1, -1):
        out[i] *= suffix
        suffix *= nums[i]
    return _join(out)


def _bisect_left(nums, target):
    lo, hi = 0, len(nums)
    while lo < hi:
        mid = (lo + hi) // 2
        if nums[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    return lo


def search_insert_position(text):  # 35
    nums, rest = _array_and_rest(text)
    return f"{_bisect_left(nums, int(rest[0]))}\n"


def binary_search(text):  # 704
    nums, rest = _array_and_rest(text)
    target = int(rest[0])
    i = _bisect_left(nums, target)
    return f"{i if i < len(nums) and nums[i] == target else -1}\n"


def intersection_ii(text):  # 350
    nums1, rest = _array_and_rest(text)
    nums2, _ = _array_and_rest("\n".join(rest))
    counts = Counter(nums1)
    result = []
    for value in nums2:
        if counts[value] > 0:
            result.append(value)
            counts[value] -= 1
    return _join(sorted(result))


def middle_of_linked_list(text):  # 876
    values, _ = _array_and_rest(text)
    return _join(values[len(values) // 2:])


def reverse_linked_list(text):  # 206
    values, _ = _array_and_rest(text)
    return _join(values[::-1])


def koko_eating_bananas(text):  # 875
    piles, rest = _array_and_rest(text)
    h = int(rest[0])
    lo, hi = 1, max(piles)
    while lo < hi:
        mid = (lo + hi) // 2
        hours = sum((p + mid - 1) // mid for p in piles)
        if hours <= h:
            hi = mid
        else:
            lo = mid + 1
    return f"{lo}\n"


def search_rotated_sorted_array(text):  # 33
    nums, rest = _array_and_rest(text)
    target = int(rest[0])
    return f"{nums.index(target) if target in nums else -1}\n"


def first_and_last_position(text):  # 34
    nums, rest = _array_and_rest(text)
    target = int(rest[0])
    lo = _bisect_left(nums, target)
    if lo == len(nums) or nums[lo] != target:
        return "-1 -1\n"
    hi = _bisect_left(nums, target + 1) - 1
    return f"{lo} {hi}\n"


def subarray_sum_equals_k(text):  # 560
    nums, rest = _array_and_rest(text)
    k = int(rest[0])
    seen = Counter({0: 1})
    prefix = count = 0
    for value in nums:
        prefix += value
        count += seen[prefix - k]
        seen[prefix] += 1
    return f"{count}\n"


def container_with_most_water(text):  # 11
    height, _ = _array_and_rest(text)
    left, right, best = 0, len(height) - 1, 0
    while left < right:
        best = max(best, min(height[left], height[right]) * (right - left))
        if height[left] < height[right]:
            left += 1
        else:
            right -= 1
    return f"{best}\n"


def evaluate_rpn(text):  # 150
    tokens = _lines(text)[0].split()
    stack = []
    for token in tokens:
        if token in "+-*/" and len(token) == 1:
            b, a = stack.pop(), stack.pop()
            if token == "+":
                stack.append(a + b)
            elif token == "-":
                stack.append(a - b)
            elif token == "*":
                stack.append(a * b)
            else:
                stack.append(int(a / b))
        else:
            stack.append(int(token))
    return f"{stack[-1]}\n"


def longest_consecutive_sequence(text):  # 128
    nums, _ = _array_and_rest(text)
    values = set(nums)
    best = 0
    for value in values:
        if value - 1 not in values:
            length = 1
            while value + length in values:
                length += 1
            best = max(best, length)
    return f"{best}\n"


def merge_two_sorted_lists(text):  # 21
    list1, rest = _array_and_rest(text)
    list2, _ = _array_and_rest("\n".join(rest))
    return _join(sorted(list1 + list2))


def linked_list_cycle(text):  # 141
    values, rest = _array_and_rest(text)
    pos = int(rest[0])
    return _bool(0 <= pos < len(values))


def remove_nth_from_end(text):  # 19
    values, rest = _array_and_rest(text)
    n = int(rest[0])
    del values[len(values) - n]
    return _join(values)


def permutation_in_string(text):  # 567
    s1, s2 = _lines(text)[:2]
    need = Counter(s1)
    width = len(s1)
    for i in range(len(s2) - width + 1):
        if Counter(s2[i:i + width]) == need:
            return _bool(True)
    return _bool(False)


def minimum_window_substring(text):  # 76
    s, t = _lines(text)[:2]
    need = Counter(t)
    missing = len(t)
    left = 0
    best = (float("inf"), 0, 0)
    for right, c in enumerate(s, start=1):
        if need[c] > 0:
            missing -= 1
        need[c] -= 1
        if missing == 0:
            while need[s[left]] < 0:
                need[s[left]] += 1
                left += 1
            if right - left < best[0]:
                best = (right - left, left, right)
            need[s[left]] += 1
            missing += 1
            left += 1
    return ("" if best[0] == float("inf") else s[best[1]:best[2]]) + "\n"


def partition_equal_subset_sum(text):  # 416
    nums, _ = _array_and_rest(text)
    total = sum(nums)
    if total % 2:
        return _bool(False)
    reachable = {0}
    for value in nums:
        reachable |= {r + value for r in reachable}
    return _bool(total // 2 in reachable)


def kth_largest(text):  # 215
    nums, rest = _array_and_rest(text)
    k = int(rest[0])
    return f"{sorted(nums, reverse=True)[k - 1]}\n"


def number_of_islands(text):  # 200
    lines = _lines(text)
    rows, cols = (int(x) for x in lines[0].split())
    grid = [list(lines[1 + r]) for r in range(rows)]
    count = 0
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == "1":
                count += 1
                queue = deque([(r, c)])
                grid[r][c] = "0"
                while queue:
                    y, x = queue.popleft()
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < rows and 0 <= nx < cols and grid[ny][nx] == "1":
                            grid[ny][nx] = "0"
                            queue.append((ny, nx))
    return f"{count}\n"


REFERENCE_SOLUTIONS = {
    "167": two_sum_ii,
    "125": valid_palindrome,
    "26": remove_duplicates,
    "643": max_average_subarray,
    "3": longest_unique_substring,
    "217": contains_duplicate,
    "242": valid_anagram,
    "20": valid_parentheses,
    "121": best_time_to_buy_and_sell,
    "70": climbing_stairs,
    "198": house_robber,
    "322": coin_change,
    "1046": last_stone_weight,
    "55": jump_game,
    "209": min_size_subarray_sum,
    "739": daily_temperatures,
    "238": product_except_self,
    "35": search_insert_position,
    "704": binary_search,
    "350": intersection_ii,
    "876": middle_of_linked_list,
    "206": reverse_linked_list,
    "875": koko_eating_bananas,
    "33": search_rotated_sorted_array,
    "34": first_and_last_position,
    "560": subarray_sum_equals_k,
    "11": container_with_most_water,
    "150": evaluate_rpn,
    "128": longest_consecutive_sequence,
    "21": merge_two_sorted_lists,
    "141": linked_list_cycle,
    "19": remove_nth_from_end,
    "567": permutation_in_string,
    "76": minimum_window_substring,
    "416": partition_equal_subset_sum,
    "215": kth_largest,
    "200": number_of_islands,
}
