# !/usr/bin/env python
# coding: utf-8
"""
数据预处理模块
计算常用技术指标：MA、EMA、MACD、RSI、布林带等
"""
import pandas as pd


def add_ma(df, periods):
    """添加简单移动平均线"""
    for p in periods:
        df[f"ma{p}"] = df["close"].rolling(p).mean()
    return df


def add_ema(df, periods):
    """添加指数移动平均线"""
    for p in periods:
        df[f"ema{p}"] = df["close"].ewm(span=p, adjust=False).mean()
    return df


def add_rsi(df, period=14):
    """添加RSI"""
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    df["rsi"] = 100 - 100 / (1 + rs)
    return df


def add_bollinger(df, period=20, std_dev=2):
    """添加布林带"""
    df["bb_mid"] = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    df["bb_upper"] = df["bb_mid"] + std_dev * std
    df["bb_lower"] = df["bb_mid"] - std_dev * std
    return df


def add_macd(df, fast=12, slow=26, signal=9):
    """添加MACD"""
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    df["macd"] = ema_fast - ema_slow
    df["macd_signal"] = df["macd"].ewm(span=signal, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    return df
