# =============================================================================
# CSI Sweet-Spot — project distributions (material types + archetype field-vs-bid)
# =============================================================================
# The "best distributions in R" companion to the Python archetype analysis.
# Reads the per-project base table + the archetype labels (same rule logic the
# dashboard computes live), merges on Contract_Id, and renders two exhibits:
#
#   1. material_distributions.png  — distribution of each of the 7 material types
#      (log10 tons/units), CSI's bids overlaid on the rest of the field.
#   2. archetype_counts.png        — project counts per archetype, field vs the
#      subset CSI bid on (CSI's selection bias by job type).
#   3. material_by_archetype.png   — material distributions colored by archetype.
#
# Colors match utils/colors.py ARCHETYPE so R and the Streamlit dashboard agree.
# Scope: presentation only; reads derived CSVs, never raw data.
#
# Run:  Rscript 02_modules/sweet_spot/scripts/2026-06-15_distributions.R
# =============================================================================

suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
  library(ggplot2)
  library(scales)
})

# --- paths (resolve relative to this script, robust to cwd) ------------------
args        <- commandArgs(trailingOnly = FALSE)
script_path <- sub("^--file=", "", args[grep("^--file=", args)])
script_dir  <- dirname(normalizePath(script_path))
OUT         <- normalizePath(file.path(script_dir, "..", "outputs"))

BASE  <- file.path(OUT, "2026-06-04_project_base.csv")
ARCH  <- file.path(OUT, "2026-06-04_project_archetypes.csv")

# --- palette (mirrors utils/colors.py) ---------------------------------------
ARCHETYPE <- c(
  "Reconstruct/Rebuild"   = "#7b3294",
  "Mill & Overlay"        = "#fdae61",
  "HMA Overlay/Resurface" = "#2c7fb8",
  "Grading/Earthwork"     = "#d7191c",
  "Aggregate/Base/Gravel" = "#abdda4",
  "Unknown/NoQty"         = "#bdbdbd",
  "Other"                 = "#999999"
)
ARCHETYPE_ORDER <- names(ARCHETYPE)
FIELD_FILL <- c("CSI bid" = "#1f4e79", "Rest of field" = "#bdbdbd")

MATERIALS <- c(
  MIX_TN_num   = "MIX  (asphalt, tons)",
  GRADE_CY_num = "GRADE  (earthwork, CY)",
  BASE_TN_num  = "BASE  (aggregate, tons)",
  SHLDR_TN_num = "SHLDR  (shoulder, tons)",
  MILL_SY_num  = "MILL  (milling, SY)",
  CRUSH_TN_num = "CRUSH  (crushed, tons)",
  STOCK_TN_num = "STOCK  (stockpile, tons)"
)

# --- load + merge ------------------------------------------------------------
base <- read.csv(BASE, stringsAsFactors = FALSE)
arch <- read.csv(ARCH, stringsAsFactors = FALSE)
df <- base %>%
  left_join(arch %>% select(Contract_Id, rule_archetype), by = "Contract_Id") %>%
  mutate(
    bid_field = ifelse(toupper(trimws(CSI_Participated)) == "TRUE",
                       "CSI bid", "Rest of field"),
    rule_archetype = factor(rule_archetype, levels = ARCHETYPE_ORDER)
  )
n_total <- nrow(df); n_bid <- sum(df$bid_field == "CSI bid")
cat(sprintf("Loaded %d projects (%d CSI bids, %d rest-of-field)\n",
            n_total, n_bid, n_total - n_bid))

# =============================================================================
# 1. Material-type distributions — CSI bids vs rest of the field
# =============================================================================
long <- df %>%
  select(Contract_Id, bid_field, all_of(names(MATERIALS))) %>%
  pivot_longer(cols = all_of(names(MATERIALS)),
               names_to = "material", values_to = "qty") %>%
  filter(!is.na(qty), qty > 0) %>%
  mutate(material = factor(MATERIALS[material], levels = MATERIALS),
         bid_field = factor(bid_field, levels = names(FIELD_FILL)))

p1 <- ggplot(long, aes(x = qty, fill = bid_field, color = bid_field)) +
  geom_density(alpha = 0.45, linewidth = 0.4) +
  facet_wrap(~ material, scales = "free", ncol = 2) +
  scale_x_log10(labels = label_comma()) +
  scale_fill_manual(values = FIELD_FILL, name = NULL) +
  scale_color_manual(values = FIELD_FILL, name = NULL) +
  labs(
    title = "Material-quantity distributions by type — CSI bids vs the rest of the field",
    subtitle = "Each panel = projects that include that material (quantity > 0), on a log10 scale",
    x = "Quantity (log10 scale)", y = "Density",
    caption = sprintf("CSI Sweet-Spot · %d projects (%d CSI bids) · source: 2026-06-04_project_base.csv",
                      n_total, n_bid)
  ) +
  theme_minimal(base_size = 12) +
  theme(
    plot.title = element_text(face = "bold", size = 13),
    plot.subtitle = element_text(color = "gray40", size = 10),
    plot.caption = element_text(color = "gray50", size = 8),
    legend.position = "top",
    strip.text = element_text(face = "bold", size = 9),
    panel.grid.minor = element_blank()
  )
ggsave(file.path(OUT, "2026-06-15_material_distributions.png"),
       p1, width = 11, height = 12, dpi = 300)
cat("Wrote 2026-06-15_material_distributions.png\n")

# =============================================================================
# 2. Archetype counts — all projects (field) vs the subset CSI bid on
# =============================================================================
counts <- df %>%
  filter(!is.na(rule_archetype)) %>%
  group_by(rule_archetype) %>%
  summarise(`All projects` = n(),
            `CSI bid` = sum(bid_field == "CSI bid"), .groups = "drop") %>%
  pivot_longer(c(`All projects`, `CSI bid`),
               names_to = "set", values_to = "n") %>%
  mutate(set = factor(set, levels = c("All projects", "CSI bid")))

p2 <- ggplot(counts, aes(x = rule_archetype, y = n, fill = set)) +
  geom_col(position = position_dodge(width = 0.75), width = 0.7) +
  geom_text(aes(label = n), position = position_dodge(width = 0.75),
            vjust = -0.3, size = 3.2, color = "gray25") +
  scale_fill_manual(values = c("All projects" = "#bdbdbd", "CSI bid" = "#1f4e79"),
                    name = NULL) +
  labs(
    title = "Projects by archetype — the whole field vs where CSI bids",
    subtitle = "Gap between bars = CSI's selection bias: it engages most on Reconstruct/Rebuild work",
    x = NULL, y = "Number of projects",
    caption = sprintf("CSI Sweet-Spot · %d projects · archetypes from the rule logic in 02_archetypes.py", n_total)
  ) +
  theme_minimal(base_size = 12) +
  theme(
    plot.title = element_text(face = "bold", size = 13),
    plot.subtitle = element_text(color = "gray40", size = 10),
    plot.caption = element_text(color = "gray50", size = 8),
    legend.position = "top",
    axis.text.x = element_text(angle = 20, hjust = 1),
    panel.grid.major.x = element_blank(),
    panel.grid.minor = element_blank()
  )
ggsave(file.path(OUT, "2026-06-15_archetype_counts.png"),
       p2, width = 10, height = 6, dpi = 300)
cat("Wrote 2026-06-15_archetype_counts.png\n")

# =============================================================================
# 3. (optional) Material distributions colored by archetype
# =============================================================================
long_arch <- df %>%
  filter(!is.na(rule_archetype)) %>%
  select(Contract_Id, rule_archetype, all_of(names(MATERIALS))) %>%
  pivot_longer(cols = all_of(names(MATERIALS)),
               names_to = "material", values_to = "qty") %>%
  filter(!is.na(qty), qty > 0) %>%
  mutate(material = factor(MATERIALS[material], levels = MATERIALS))

p3 <- ggplot(long_arch, aes(x = qty, fill = rule_archetype)) +
  geom_density(alpha = 0.4, color = NA) +
  facet_wrap(~ material, scales = "free", ncol = 2) +
  scale_x_log10(labels = label_comma()) +
  scale_fill_manual(values = ARCHETYPE, name = "Archetype") +
  labs(
    title = "Material-quantity distributions by archetype",
    subtitle = "Where each archetype's volume lives across the 7 material types (log10 scale)",
    x = "Quantity (log10 scale)", y = "Density",
    caption = sprintf("CSI Sweet-Spot · %d projects with quantities", sum(!is.na(df$rule_archetype) & df$rule_archetype != "Unknown/NoQty"))
  ) +
  theme_minimal(base_size = 12) +
  theme(
    plot.title = element_text(face = "bold", size = 13),
    plot.subtitle = element_text(color = "gray40", size = 10),
    plot.caption = element_text(color = "gray50", size = 8),
    legend.position = "top",
    strip.text = element_text(face = "bold", size = 9),
    panel.grid.minor = element_blank()
  )
ggsave(file.path(OUT, "2026-06-15_material_by_archetype.png"),
       p3, width = 11, height = 12, dpi = 300)
cat("Wrote 2026-06-15_material_by_archetype.png\n")

cat("Done. PNGs in:", OUT, "\n")
