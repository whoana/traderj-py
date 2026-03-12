import type { CandleData } from "@/types/chart";

export interface EMAPoint {
  time: number;
  value: number;
}

export interface BBPoint {
  time: number;
  upper: number;
  middle: number;
  lower: number;
}

export interface RSIPoint {
  time: number;
  value: number;
}

export function calculateEMA(data: CandleData[], period: number): EMAPoint[] {
  if (data.length < period) return [];

  const result: EMAPoint[] = [];
  const multiplier = 2 / (period + 1);

  // First value = SMA of first `period` closes
  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += data[i].close;
  }
  let ema = sum / period;
  result.push({ time: data[period - 1].time, value: ema });

  for (let i = period; i < data.length; i++) {
    ema = (data[i].close - ema) * multiplier + ema;
    result.push({ time: data[i].time, value: ema });
  }

  return result;
}

export function calculateBB(
  data: CandleData[],
  period: number = 20,
  stdDevMultiplier: number = 2,
): BBPoint[] {
  if (data.length < period) return [];

  const result: BBPoint[] = [];

  for (let i = period - 1; i < data.length; i++) {
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) {
      sum += data[j].close;
    }
    const middle = sum / period;

    let sqSum = 0;
    for (let j = i - period + 1; j <= i; j++) {
      sqSum += (data[j].close - middle) ** 2;
    }
    const stdDev = Math.sqrt(sqSum / period);

    result.push({
      time: data[i].time,
      upper: middle + stdDevMultiplier * stdDev,
      middle,
      lower: middle - stdDevMultiplier * stdDev,
    });
  }

  return result;
}

export function calculateRSI(data: CandleData[], period: number = 14): RSIPoint[] {
  if (data.length < period + 1) return [];

  const result: RSIPoint[] = [];

  // Calculate initial gains and losses
  let avgGain = 0;
  let avgLoss = 0;
  for (let i = 1; i <= period; i++) {
    const change = data[i].close - data[i - 1].close;
    if (change > 0) avgGain += change;
    else avgLoss += Math.abs(change);
  }
  avgGain /= period;
  avgLoss /= period;

  const rsi = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  result.push({ time: data[period].time, value: rsi });

  // Wilder's smoothing
  for (let i = period + 1; i < data.length; i++) {
    const change = data[i].close - data[i - 1].close;
    const gain = change > 0 ? change : 0;
    const loss = change < 0 ? Math.abs(change) : 0;

    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;

    const val = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
    result.push({ time: data[i].time, value: val });
  }

  return result;
}
