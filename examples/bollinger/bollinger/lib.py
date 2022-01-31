import os

import pandas as pd
import pandera as pa
from dagster_pandera import pandera_schema_to_dagster_type
from pandera.typing import Series

# ****************************************************************************
# ***** TYPES ****************************************************************


class Sp500Prices(pa.SchemaModel):
    name: Series[str] = pa.Field()
    date: Series[pd.Timestamp] = pa.Field()
    open: Series[float] = pa.Field(ge=0)
    high: Series[float] = pa.Field(ge=0)
    low: Series[float] = pa.Field(ge=0)
    close: Series[float] = pa.Field(ge=0)
    volume: Series[int] = pa.Field(ge=0)


Sp500PricesDgType = pandera_schema_to_dagster_type(
    Sp500Prices,
    description="Historical stock prices for the S&P 500.",
    column_descriptions={
        "name": "Ticker symbol of stock",
        "date": "Date of prices",
        "open": "Price at market open",
        "high": "Highest price of the day",
        "low": "Lowest price of the day",
        "close": "Price at market close",
        "volume": "Number of shares traded for day",
    },
)


class Bollinger(pa.SchemaModel):
    name: Series[str] = pa.Field()
    date: Series[pd.Timestamp] = pa.Field()
    upper: Series[float] = pa.Field()
    lower: Series[float] = pa.Field()


BollingerDgType = pandera_schema_to_dagster_type(
    Bollinger,
    description="Bollinger bands for a set of stock prices.",
    column_descriptions={
        "name": "Ticker symbol of stock",
        "date": "Date of prices",
        "upper": "Upper Bollinger band",
        "lower": "Lower Bollinger band",
    },
)

cat = pd.Categorical(["high", "low"], ordered=False)


class AnomalousEvents(pa.SchemaModel):
    date: Series[pd.Timestamp] = pa.Field()
    name: Series[str] = pa.Field()
    event: Series[pd.CategoricalDtype] = pa.Field()


AnomalousEventsDgType = pandera_schema_to_dagster_type(
    AnomalousEvents,
    description="""
        Anomalous price events, defined by a day on which a stock's price strayed above or below its
        Bollinger bands.
    """.replace(
        r"\n\s+", " "
    ),
    column_descriptions={
        "date": "Date of event",
        "name": "Ticker symbol of stock",
        "event": "Type of event: 'high' or 'low'",
    },
)

# ****************************************************************************
# ***** FUNCTIONS ************************************************************

# TODO: need a better solution
DATA_ROOT = os.path.join(os.path.dirname(__file__), "../data")


def resolve_data_path(relative_path: str):
    return os.path.join(DATA_ROOT, relative_path)


def load_sp500_prices() -> pd.DataFrame:
    path = resolve_data_path("all_stocks_5yr.csv")
    df = pd.read_csv(path, parse_dates=["date"])
    df = df.rename(columns={"Name": "name"})
    df = df.dropna()
    return df


def compute_bollinger(
    df: pd.DataFrame, rate: int = 30, sigma: float = 2.0, dropna=True
) -> pd.DataFrame:
    price = df["close"]
    rma = price.rolling(window=rate).mean()
    rstd = price.rolling(window=rate).std()
    upper = rma + sigma * rstd
    lower = rma - sigma * rstd
    odf = pd.DataFrame({"name": df["name"], "date": df["date"], "upper": upper, "lower": lower})
    if dropna:
        odf = odf.dropna()
    return odf


def compute_bollinger_multi(df: pd.DataFrame, dropna: bool = True):
    odf = df.groupby("name").apply(lambda idf: compute_bollinger(idf, dropna=False))
    return odf.dropna().reset_index() if dropna else odf


EVENT_TYPE = pd.CategoricalDtype(["high", "low"], ordered=False)


def compute_anomalous_events(df_prices: pd.DataFrame, df_bollinger: pd.DataFrame):
    df = pd.concat([df_prices, df_bollinger.add_prefix("bol_")], axis=1)
    df["event"] = pd.Series(pd.NA, index=df.index, dtype=EVENT_TYPE)
    df["event"][df["close"] > df["bol_upper"]] = "high"
    df["event"][df["close"] < df["bol_lower"]] = "low"
    return df[df["event"].notna()][["name", "date", "event"]].reset_index()
