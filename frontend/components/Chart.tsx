"use client";
import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  CandlestickSeries,
  HistogramSeries,
  createSeriesMarkers,
  UTCTimestamp,
  SeriesMarker
} from "lightweight-charts";

export function Chart({ candles, signals, features }: { candles: any[], signals: any[], features?: any }) {
  const chartContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!chartContainerRef.current || !candles || candles.length === 0) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#11141c' },
        textColor: '#d1d4dc',
      },
      grid: {
        vertLines: { color: 'rgba(42, 46, 57, 0.5)' },
        horzLines: { color: 'rgba(42, 46, 57, 0.5)' },
      },
      width: chartContainerRef.current.clientWidth || 800,
      height: 400,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      }
    });

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: '#26a69a',
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: '', // set as an overlay by setting a blank priceScaleId
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.8, // highest point of the series will be at 80% of the chart
        bottom: 0,
      },
    });

    const formattedData = candles.map(c => ({
      time: c.timestamp as UTCTimestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close
    }));
    candlestickSeries.setData(formattedData);

    const volumeData = candles.map(c => ({
      time: c.timestamp as UTCTimestamp,
      value: c.volume || 0,
      color: c.close > c.open ? 'rgba(38, 166, 154, 0.5)' : 'rgba(239, 83, 80, 0.5)'
    }));
    volumeSeries.setData(volumeData);

    if (signals && signals.length > 0) {
      // Filter out neutral / NO_TRADE signals
      const activeSignals = signals.filter(s => s && s.action !== 'NO_TRADE' && s.direction);
      const lastCandleTs = candles[candles.length - 1].timestamp;

      const markers: SeriesMarker<UTCTimestamp>[] = activeSignals.map(s => ({
        // Ensure marker snaps to a valid candle timestamp on chart
        time: (s.candle_timestamp || lastCandleTs) as UTCTimestamp,
        position: s.direction === 'LONG' ? 'belowBar' : 'aboveBar',
        color: s.direction === 'LONG' ? '#26a69a' : '#ef5350',
        shape: s.direction === 'LONG' ? 'arrowUp' : 'arrowDown',
        text: s.direction === 'LONG' ? 'BUY' : 'SELL',
      }));
      markers.sort((a, b) => (a.time as number) - (b.time as number));
      createSeriesMarkers(candlestickSeries, markers);
    }

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [candles, signals]);

  return <div ref={chartContainerRef} style={{ width: '100%', marginBottom: 16 }} />;
}
