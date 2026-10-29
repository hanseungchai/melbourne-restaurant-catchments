"""Model error vs Google for single trips (concepts/reachability.md RCH-23 (b)): model error only; departure noise
(RCH-23 (a)) is drawn apart.

Google's time given the model's predicted time p is p x exp(r), with r = log(google_s / model_s) taken from the
TRIP_ERROR_K_NEIGHBOURS fit pairs nearest to p in log time, inside the trip's group. Groups: transit departures
before TRIP_ERROR_NIGHT_END_MIN are "night" (Google waits for the first service there), the rest "day"; drive is one
group. A group with fewer fit pairs than K falls back to all fit pairs. Out-of-fold calibration:
diagnostics/trip_error_conditional.py.
"""
import numpy as np
import pandas as pd

import config

SECONDS_PER_MIN = 60
DAY_GROUP, NIGHT_GROUP, ALL_GROUP = "day", "night", "all"
TRANSIT_MODE = "transit"


def error_group(mode, departure_min_of_day):
    """Each trip's group: transit day / night by departure minute of day; any other mode one group."""
    departure_min_of_day = np.asarray(departure_min_of_day)
    if mode != TRANSIT_MODE:
        return np.full(departure_min_of_day.shape, ALL_GROUP, dtype=object)
    return np.where(departure_min_of_day < config.TRIP_ERROR_NIGHT_END_MIN, NIGHT_GROUP, DAY_GROUP).astype(object)


def fit_trip_error(mode, model_s, google_s, departure_min_of_day):
    """Fit table: per group, fit pairs sorted by log(predicted) with their residuals r = log(google / predicted)."""
    model_s = np.maximum(np.asarray(model_s, dtype=float), config.TRIP_ERROR_MIN_MODEL_S)
    fit_df = pd.DataFrame({"group": error_group(mode, departure_min_of_day), "log_model": np.log(model_s),
                           "residual": np.log(np.asarray(google_s, dtype=float) / model_s)})
    groups = {name: part.sort_values("log_model") for name, part in fit_df.groupby("group")}
    groups[ALL_GROUP] = fit_df.sort_values("log_model")
    return {"mode": mode, "groups": {name: (part.log_model.to_numpy(), part.residual.to_numpy()) for name, part in groups.items()}}


def _neighbour_residuals(fit, group, log_query):
    log_model, residual = fit["groups"].get(group, (np.empty(0), np.empty(0)))
    if len(log_model) < config.TRIP_ERROR_K_NEIGHBOURS:
        log_model, residual = fit["groups"][ALL_GROUP]
    k = min(config.TRIP_ERROR_K_NEIGHBOURS, len(log_model))
    centre = np.searchsorted(log_model, log_query)
    window = np.arange(max(0, centre - k), min(len(log_model), centre + k))
    nearest = window[np.argsort(np.abs(log_model[window] - log_query), kind="stable")[:k]]
    return residual[nearest]


def google_draws(fit, predicted_s, departure_min_of_day):
    """Per trip, the K possible Google times (seconds) given its predicted time: rows = trips, columns = draws."""
    predicted_s = np.maximum(np.atleast_1d(np.asarray(predicted_s, dtype=float)), config.TRIP_ERROR_MIN_MODEL_S)
    groups = error_group(fit["mode"], np.broadcast_to(departure_min_of_day, predicted_s.shape))
    return np.array([p * np.exp(_neighbour_residuals(fit, g, np.log(p))) for p, g in zip(predicted_s, groups)])


def google_quantiles(fit, predicted_s, departure_min_of_day, levels):
    """Quantiles of Google's time (seconds) per trip; columns follow levels."""
    return np.quantile(google_draws(fit, predicted_s, departure_min_of_day), levels, axis=1).T


def band_probability(fit, predicted_s, departure_min_of_day, cut_min):
    """P(Google's rounded minute <= cut_min) per trip, as the band checks read Google."""
    draws = google_draws(fit, predicted_s, departure_min_of_day)
    return (np.round(draws / SECONDS_PER_MIN) <= cut_min).mean(axis=1)
