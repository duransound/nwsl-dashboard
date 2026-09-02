"""Two xG models on the same 3,490 NWSL 2023 shots.

  A  "location only"  -- distance, angle, body part, shot type.
     Approximates what ASA's public model sees: where the shot was taken from
     and how, and nothing about who was standing in the way.

  B  "+ defensive context" -- everything in A, plus what the freeze frame
     carries: defenders inside the shooting cone, distance to the nearest
     defender, and how far off the line the keeper is.

The gap between them, per shot, is the price of the thing A cannot see.

Both are logistic regressions with 5-fold cross-validated predictions, so the
comparison is out-of-sample and neither model is scored on shots it was fit on.
"""
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import log_loss, roc_auc_score

df = pd.read_csv("shots_2023.csv")
df["nearest_defender"] = df["nearest_defender"].fillna(df["nearest_defender"].median())
df["gk_off_line"] = df["gk_off_line"].fillna(df["gk_off_line"].median())
df["gk_lateral_abs"] = df["gk_lateral"].abs().fillna(0)

# Distance and angle both enter non-linearly in every published xG model;
# logs and an interaction get most of that without fitting a spline.
df["log_dist"] = np.log1p(df["distance"])
df["inv_dist"] = 1.0 / df["distance"].clip(lower=1)
df["log_angle"] = np.log1p(df["angle"])

bp = pd.get_dummies(df["body_part"], prefix="bp", drop_first=True).astype(float)
st_ = pd.get_dummies(df["shot_type"], prefix="st", drop_first=True).astype(float)

LOC = ["distance", "log_dist", "inv_dist", "angle", "log_angle"]
DEF = ["defenders_in_cone", "nearest_defender", "gk_off_line", "gk_lateral_abs",
       "under_pressure"]
df["under_pressure"] = df["under_pressure"].astype(int)

XA = pd.concat([df[LOC], bp, st_], axis=1).values
XB = pd.concat([df[LOC + DEF], bp, st_], axis=1).values
y = df["goal"].values

cv = StratifiedKFold(5, shuffle=True, random_state=7)
def fit(X):
    pipe = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0))
    return cross_val_predict(pipe, X, y, cv=cv, method="predict_proba")[:, 1]

pa, pb = fit(XA), fit(XB)
base = np.full_like(y, y.mean(), dtype=float)

print(f"{len(df)} shots, {y.sum()} goals ({y.mean():.3f} conversion)\n")
print(f"{'model':<28}{'log loss':>10}{'AUC':>8}")
print(f"{'baseline (mean rate)':<28}{log_loss(y, base):>10.4f}{'--':>8}")
print(f"{'A  location only':<28}{log_loss(y, pa):>10.4f}{roc_auc_score(y, pa):>8.4f}")
print(f"{'B  + defensive context':<28}{log_loss(y, pb):>10.4f}{roc_auc_score(y, pb):>8.4f}")
print(f"{'StatsBomb xG (reference)':<28}{log_loss(y, df.sb_xg.clip(1e-6,1-1e-6)):>10.4f}"
      f"{roc_auc_score(y, df.sb_xg):>8.4f}")

df["xg_loc"], df["xg_def"] = pa, pb
df["context"] = df["xg_def"] - df["xg_loc"]      # what the freeze frame is worth
df.to_csv("shots_2023_modelled.csv", index=False)

print("\ncoefficients of the defensive block (model B, standardised):")
pipe = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0)).fit(XB, y)
names = LOC + DEF + list(bp.columns) + list(st_.columns)
coefs = pipe[-1].coef_[0]
for n in DEF:
    print(f"  {n:<20}{coefs[names.index(n)]:+.3f}")
