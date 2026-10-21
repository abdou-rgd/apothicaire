#!/usr/bin/env Rscript
# Independent NCA of the frozen exercises with PKNCA (T-101, FROZEN_SET.md 5.4).
#
# The gold of a frozen exercise is the output of Caladrius itself. This script recomputes the NCA of every exercise
# with PKNCA, the package Caladrius's public NCA oracle is built on (caladrius oracle/scripts/nca_pknca.R, same
# version 0.12.1, same explicit options), so that bench/pknca_check.py can compare the two outside the engine.
#
# Usage, from the apothicaire repository root:
#   Rscript bench/pknca/frozen_nca_pknca.R bench/frozen/demo/exercises bench/frozen/demo/pknca/pknca.csv
#
# Writes (deterministically, LF line endings, no timestamps):
#   <out>                    long table: exercise,method,parameter,value  (values in the units of the Caladrius gold)
#   <out minus .csv>.json    R and package versions, options, preprocessing, unit factors per exercise
#
# Each exercise is read from its data.csv and meta.json (dose, route, infusion duration, units). Values below the
# limit of quantification are written as 0 in the CSV; PKNCA's default BLQ rule (first kept, middle dropped, last
# kept) is the engine's default and is set explicitly. Units: the dose is converted to the mass unit of the
# concentration (ug for ng/mL, mg for mg/L) before PKNCA sees it, so CL comes out in L/time and V in L, as in the
# gold computed with options.units; the dose-normalised values (.dn) are converted back to the dose unit of the
# exercise. IV bolus profiles have no sample at the dose time: as in the caladrius oracle, C0 is back-extrapolated
# (pk.calc.c0) and added at t = 0 for areas and derived values; Cmax, Tmax, Tfirst and Cmax.dn come from the
# observed samples, and the added point is kept out of the terminal phase.
#
# PKNCA is AGPL-3 and is used as an external tool only; nothing of it is copied into this repository.

suppressPackageStartupMessages({
  library(PKNCA)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2L) stop("usage: Rscript frozen_nca_pknca.R <exercises dir> <out.csv>")
ex_root <- args[[1]]
out_csv <- args[[2]]
dir.create(dirname(out_csv), showWarnings = FALSE, recursive = TRUE)

write_lines_lf <- function(lines, path) {
  con <- file(path, open = "wb")
  on.exit(close(con))
  writeLines(lines, con, sep = "\n", useBytes = TRUE)
}
num <- function(x) ifelse(is.na(x), "", sprintf("%.15g", x))

# ---------------------------------------------------------------- explicit options (those of the caladrius oracle)
base_options <- list(
  conc.na = "drop",
  conc.blq = list(first = "keep", middle = "drop", last = "keep"),
  first.tmax = TRUE,
  allow.tmax.in.half.life = FALSE,
  min.hl.points = 3,
  adj.r.squared.factor = 1e-4,
  min.hl.r.squared = 0.9,
  min.span.ratio = 2,
  max.aucinf.pext = 20,
  max.missing = 0.5
)
methods <- c(linear = "linear", lin_up_log_down = "lin up/log down")

# ---------------------------------------------------------------- parameters
param_dn <- c("cmax.dn", "clast.obs.dn", "auclast.dn", "aucall.dn", "aucinf.obs.dn",
              "aucinf.pred.dn", "aumclast.dn", "aumcall.dn", "aumcinf.obs.dn", "aumcinf.pred.dn")
param_core <- c(
  "cmax", "tmax", "tfirst", "tlast", "clast.obs",
  "lambda.z", "r.squared", "adj.r.squared", "lambda.z.time.first",
  "lambda.z.time.last", "lambda.z.n.points", "clast.pred", "half.life", "span.ratio",
  "auclast", "aucall", "aumclast", "aumcall",
  "aucinf.obs", "aucinf.pred", "aumcinf.obs", "aumcinf.pred",
  "aucpext.obs", "aucpext.pred"
)
param_ev <- c(param_core, "tlag", "cl.obs", "cl.pred", "mrt.obs", "mrt.pred", "mrt.last",
              "vz.obs", "vz.pred", "vss.obs", "vss.pred", param_dn)
param_iv <- c("c0", param_core, "cl.obs", "cl.pred", "mrt.iv.obs", "mrt.iv.pred", "mrt.iv.last", "vz.obs", "vz.pred",
              "vss.iv.obs", "vss.iv.pred", "vss.iv.last", "vss.obs", "vss.pred", param_dn)
param_inf <- c(param_core, "cl.obs", "cl.pred", "mrt.iv.obs", "mrt.iv.pred", "mrt.iv.last", "vz.obs", "vz.pred",
               "vss.iv.obs", "vss.iv.pred", "vss.iv.last", "vss.obs", "vss.pred", param_dn)
derived_aumcpext <- c("aumcpext.obs", "aumcpext.pred")       # 100 * (1 - AUMClast / AUMCinf), not a PKNCA parameter

# mass of the dose unit, in the mass unit of the concentration: ug for ng/mL (= ug/L), mg for mg/L
dose_factor <- function(dose_unit, conc_unit) {
  to_mg <- c(mg = 1, ug = 1e-3)
  conc_mass_mg <- c("mg/L" = 1, "ng/mL" = 1e-3)
  if (!(dose_unit %in% names(to_mg)) || !(conc_unit %in% names(conc_mass_mg))) stop("unknown unit ", dose_unit, " / ", conc_unit)
  unname(to_mg[dose_unit] / conc_mass_mg[conc_unit])
}

run_pknca <- function(profile, route, duration, dose, auc_method, params) {
  if ("excl_hl" %in% names(profile)) {
    conc <- PKNCAconc(profile, conc ~ time | subject, exclude_half.life = "excl_hl")
  } else {
    conc <- PKNCAconc(profile, conc ~ time | subject)
  }
  dose_rows <- data.frame(subject = 1L, time = 0, dose = dose)
  if (duration > 0) {
    dose_rows$duration <- duration
    d <- PKNCAdose(dose_rows, dose ~ time | subject, route = route, duration = "duration")
  } else {
    d <- PKNCAdose(dose_rows, dose ~ time | subject, route = route)
  }
  iv <- data.frame(start = 0, end = Inf)
  for (p in params) iv[[p]] <- TRUE
  opts <- base_options
  opts$auc.method <- auc_method
  res <- suppressWarnings(as.data.frame(pk.nca(PKNCAdata(conc, d, intervals = iv, options = opts))))
  res <- res[res$PPTESTCD %in% params, c("PPTESTCD", "PPORRES")]
  setNames(res$PPORRES, res$PPTESTCD)[params]                  # NA for a parameter PKNCA did not return
}

# IV bolus without a sample at the dose time: the C0 point of the caladrius oracle (augment_with_c0).
augment_with_c0 <- function(p) {
  c0 <- pk.calc.c0(p$conc, p$time, time.dose = 0)
  p$excl_hl <- p$time == p$time[which.max(p$conc)]
  rbind(data.frame(subject = 1L, time = 0, conc = c0, excl_hl = TRUE), p)
}

exercise_rows <- function(dir) {
  meta <- fromJSON(file.path(dir, "meta.json"), simplifyVector = FALSE)
  raw <- read.csv(file.path(dir, "data.csv"), check.names = FALSE)
  profile <- data.frame(subject = 1L, time = as.numeric(raw[[1]]), conc = as.numeric(raw[[2]]))
  route_meta <- meta$route
  duration <- 0
  if (is.list(route_meta)) { duration <- as.numeric(route_meta$iv_infusion$duration); kind <- "iv_infusion" }
  else kind <- route_meta
  route <- if (kind == "extravascular") "extravascular" else "intravascular"
  params <- switch(kind, extravascular = param_ev, iv_bolus = param_iv, iv_infusion = param_inf)
  f <- dose_factor(meta$dose$unit, meta$units$conc)
  dose <- as.numeric(meta$dose$amount) * f
  bolus_no_t0 <- kind == "iv_bolus" && !any(profile$time == 0)
  rows <- list()
  for (m in names(methods)) {
    if (bolus_no_t0) {
      observed <- run_pknca(profile, route, duration, dose, methods[[m]], params)
      augmented <- run_pknca(augment_with_c0(profile), route, duration, dose, methods[[m]], params)
      stopifnot(isTRUE(all.equal(unname(observed["lambda.z"]), unname(augmented["lambda.z"]), tolerance = 1e-12)))
      v <- augmented
      keep <- c("cmax", "tmax", "tfirst", "cmax.dn")
      v[keep] <- observed[keep]
    } else {
      v <- run_pknca(profile, route, duration, dose, methods[[m]], params)
    }
    dn <- names(v) %in% param_dn
    v[dn] <- v[dn] * f                                          # per converted dose unit -> per dose unit of the exercise
    v["aumcpext.obs"] <- 100 * (1 - v[["aumclast"]] / v[["aumcinf.obs"]])
    v["aumcpext.pred"] <- 100 * (1 - v[["aumclast"]] / v[["aumcinf.pred"]])
    rows[[m]] <- data.frame(exercise = meta$id, method = m, parameter = names(v), value = unname(v), stringsAsFactors = FALSE)
  }
  list(rows = do.call(rbind, rows),
       info = list(id = meta$id, route = kind, infusion_duration = duration, dose = meta$dose$amount, dose_unit = meta$dose$unit,
                   conc_unit = meta$units$conc, dose_factor = f, c0_added = bolus_no_t0))
}

dirs <- sort(list.dirs(ex_root, recursive = FALSE))
all_rows <- list(); infos <- list()
for (d in dirs) {
  r <- exercise_rows(d)
  all_rows[[length(all_rows) + 1L]] <- r$rows
  infos[[length(infos) + 1L]] <- r$info
}
res <- do.call(rbind, all_rows)
write_lines_lf(c("exercise,method,parameter,value", sprintf("%s,%s,%s,%s", res$exercise, res$method, res$parameter, num(res$value))), out_csv)

versions <- list(R = R.version.string, PKNCA = as.character(packageVersion("PKNCA")),
                 jsonlite = as.character(packageVersion("jsonlite")))
info <- list(
  schema = 1L, generated_by = "bench/pknca/frozen_nca_pknca.R", exercises_dir = ex_root, versions = versions,
  pknca_options = base_options, auc_methods = as.list(methods),
  preprocessing = list(
    "BLQ values are written as 0; PKNCA conc.blq first = keep, middle = drop, last = keep (the engine's default policy)",
    "the dose is converted to the mass unit of the concentration (dose_factor) so that CL is in L/time and V in L; .dn values are converted back to the exercise's dose unit",
    "IV bolus without a sample at t = 0: C0 from pk.calc.c0 (default method chain) added at t = 0 for areas and derived values; cmax, tmax, tfirst and cmax.dn from the observed samples; the added point and the observed Cmax point excluded from the terminal phase; lambda.z asserted identical with and without the added point",
    "aumcpext.obs and aumcpext.pred are computed by this script as 100 * (1 - aumclast / aumcinf), as in the caladrius oracle"),
  exercises = infos, n_values = nrow(res), n_na = sum(is.na(res$value)))
write_lines_lf(toJSON(info, pretty = TRUE, auto_unbox = TRUE, digits = NA, null = "null"), sub("\\.csv$", ".json", out_csv))
cat(sprintf("%d exercises, %d values (%d NA) | %s | PKNCA %s\n", length(dirs), nrow(res), sum(is.na(res$value)),
            versions$R, versions$PKNCA))
