-- The token bucket for one key, run atomically by Redis (ADR-0006, ADR-0007). Unit-tested against
-- fakeredis.
--
-- The balance is kept in units of 1/60000 token: one millisecond at tokens_per_minute refills
-- exactly tokens_per_minute units, so every stored value is an integer below 2^53 and exact as a
-- Lua number. The caller passes the current time from its injected clock; the script never reads
-- the server clock.
--
-- KEYS[1]  the bucket: a hash with balance_units and updated_milliseconds
-- ARGV[1]  now_milliseconds
-- ARGV[2]  tokens_per_minute, which is also the refill in units per millisecond
-- ARGV[3]  capacity_units
-- ARGV[4]  floor_units: the lowest balance a charge can reach (negative)
-- ARGV[5]  mode: "reserve" or "settle"
-- ARGV[6]  amount_units: reserve takes it only if the balance covers it; settle subtracts it, and
--          a negative amount is a refund
-- ARGV[7]  expiry_margin_milliseconds
-- Returns {allowed (1 or 0), "<balance_units>/60000"}: the balance as an exact fraction of tokens.

local now = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local capacity = tonumber(ARGV[3])
local floor_units = tonumber(ARGV[4])
local mode = ARGV[5]
local amount = tonumber(ARGV[6])
local margin = tonumber(ARGV[7])

local balance = capacity -- a new or expired bucket starts full
local updated = now
local stored = redis.call("HMGET", KEYS[1], "balance_units", "updated_milliseconds")
if stored[1] and stored[2] then
  balance = tonumber(stored[1])
  updated = tonumber(stored[2])
  -- A clock that steps back refills nothing, and the timestamp never moves back, so the same
  -- interval is never refilled twice.
  local elapsed = math.max(0, now - updated)
  updated = math.max(updated, now)
  local missing = capacity - balance
  -- floor(q) + 1 is at least ceil(q): long enough to refill completely. Clamping first keeps the
  -- product small after a long idle period. Even clamped, it can pass 2^53 at the largest rate and
  -- deepest debt, but only when the true refill is at least `missing`; rounding cannot move it
  -- below that exact value, so the comparison holds and the inexact product is never stored.
  local enough = math.floor(missing / rate) + 1
  if elapsed > enough then
    elapsed = enough
  end
  local refill = elapsed * rate
  if refill >= missing then
    balance = capacity
  else
    balance = balance + refill
  end
end

local allowed = 0
if mode == "reserve" then
  if balance >= amount then
    balance = balance - amount
    allowed = 1
  end
elseif mode == "settle" then
  -- Compare against exact gaps, so no value outside [floor_units, capacity] is ever computed.
  if amount >= balance - floor_units then
    balance = floor_units
  elseif -amount >= capacity - balance then
    balance = capacity
  else
    balance = balance - amount
  end
else
  return redis.error_reply("token_bucket: unknown mode")
end

redis.call("HSET", KEYS[1],
  "balance_units", string.format("%.0f", balance),
  "updated_milliseconds", string.format("%.0f", updated))
-- A missing key starts full, so the key expires only after the bucket would be full anyway: the
-- wait until the caller's clock reaches the stored timestamp, the refill time, and a margin for
-- clock differences between hosts.
local expiry = (updated - now) + math.floor((capacity - balance) / rate) + 1 + margin
redis.call("PEXPIRE", KEYS[1], string.format("%.0f", expiry))
return {allowed, string.format("%.0f/60000", balance)}
