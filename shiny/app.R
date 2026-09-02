# -----------------------------------------------------------------------------
# NWSL Finishing Explorer
#
# A Shiny companion to the static dashboard at
# https://duransound.github.io/nwsl-dashboard/ — deliberately doing the one
# thing that dashboard cannot.
#
# The static site bakes its numbers at build time, so every threshold in it is
# a decision someone else already made: the qualification bar is 30 minutes per
# game the team has played, the shot floor is 10, penalties are always out.
# Those are defensible defaults and they are still arguments. This app hands
# them to the reader as controls and re-derives everything live, which is the
# actual case for Shiny over a rendered page.
#
# RUN
#   install.packages(c("shiny", "ggplot2", "dplyr", "DT", "httr", "jsonlite"))
#   shiny::runApp()
#
# DEPLOY (free tier)
#   install.packages("rsconnect")
#   rsconnect::deployApp(appName = "nwsl-finishing-explorer")
#   # appName is not optional in practice -- without it the app is named after
#   # this directory ("shiny") and the public URL says nothing about it.
#
# DATA
#   Live from the American Soccer Analysis API when it is reachable. Falls back
#   to data/nwsl_2026_snapshot.csv otherwise, and says which one it used rather
#   than quietly showing stale numbers — the same rule the warehouse follows
#   when a load fails.
# -----------------------------------------------------------------------------

library(shiny)
library(ggplot2)
library(dplyr)
library(DT)

BASE <- "https://app.americansocceranalysis.com/api/v1/nwsl"

# Brand palette, matching the dashboard (Design Guidelines §0, round 20).
AMBER <- "#C98A2E"; RED <- "#e34948"; INK <- "#1F1B16"; MUTED <- "#9aa5b1"
GRID  <- "#e4e2dd"; PAPER <- "#faf9f7"

# ---------------------------------------------------------------- data access

asa_get <- function(path, query = list()) {
  r <- httr::GET(paste0(BASE, "/", path), query = query, httr::timeout(25))
  httr::stop_for_status(r)
  jsonlite::fromJSON(httr::content(r, "text", encoding = "UTF-8"),
                     simplifyDataFrame = TRUE)
}

#' Pull a season from ASA and reduce it to one row per player, penalties out.
#'
#' npxG is derived the same way the Python pipeline derives it: ask
#' /players/xgoals twice, once unfiltered and once with shot_pattern=Penalty,
#' and subtract. ASA publishes no non-penalty field.
fetch_live <- function(season) {
  teams   <- asa_get("teams")
  tx      <- asa_get("teams/xgoals", list(season_name = season))
  players <- asa_get("players")
  floor_m <- 0

  all_shots <- asa_get("players/xgoals",
                       list(season_name = season, minimum_minutes = floor_m))
  pens <- asa_get("players/xgoals",
                  list(season_name = season, minimum_minutes = floor_m,
                       shot_pattern = "Penalty"))

  # team_id arrives as a list column on player endpoints and a bare string on
  # team endpoints — and for a mid-season transfer the list holds two clubs in
  # an order that means nothing. Taking the first element is what the static
  # pipeline does before it resolves the split properly; flagged rather than
  # hidden, since this app has no budget for the extra per-player calls.
  first_team <- function(x) vapply(x, function(v) as.character(v)[1], character(1))

  games <- setNames(
    dplyr::coalesce(tx$count_games, tx$games, tx$games_played),
    tx$team_id)
  abbr  <- setNames(teams$team_abbreviation, teams$team_id)
  names_by_id <- setNames(players$player_name, players$player_id)

  pen_idx <- match(all_shots$player_id, pens$player_id)
  zero <- function(v) ifelse(is.na(v), 0, v)

  tid <- first_team(all_shots$team_id)
  data.frame(
    player     = unname(names_by_id[all_shots$player_id]),
    team       = unname(abbr[tid]),
    team_games = unname(zero(games[tid])),
    minutes    = all_shots$minutes_played,
    position   = all_shots$general_position,
    np_shots   = pmax(all_shots$shots  - zero(pens$shots[pen_idx]), 0),
    np_goals   = pmax(all_shots$goals  - zero(pens$goals[pen_idx]), 0),
    npxg       = pmax(all_shots$xgoals - zero(pens$xgoals[pen_idx]), 0),
    np_xplace  = all_shots$xplace - zero(pens$xplace[pen_idx]),
    xassists   = all_shots$xassists,
    stringsAsFactors = FALSE
  )
}

load_players <- function(season) {
  live <- try(fetch_live(season), silent = TRUE)
  if (!inherits(live, "try-error") && nrow(live) > 0) {
    list(data = live, source = sprintf("live from the ASA API (%s)", season))
  } else {
    list(data = read.csv("data/nwsl_2026_snapshot.csv", stringsAsFactors = FALSE),
         source = "bundled snapshot - the ASA API was unreachable")
  }
}

# ------------------------------------------------------------------------- ui

ui <- fluidPage(
  tags$head(tags$style(HTML(sprintf("
    body { background: %s; color: %s;
           font-family: Karla, -apple-system, 'Segoe UI', Helvetica, sans-serif; }
    h2 { font-family: Fraunces, Georgia, serif; font-weight: 600;
         letter-spacing: -.01em; margin-bottom: .2rem; }
    .lede { color:#5b5750; max-width: 62ch; margin-bottom: 1.2rem; }
    .src  { font-size: 12px; color:#8C8377; margin-top: .6rem; }
    .well { background:#fff; border:1px solid %s; box-shadow:none; }
  ", PAPER, INK, GRID)))),

  h2("NWSL Finishing Explorer"),
  div(class = "lede",
      "Every threshold on the static dashboard is a judgement call someone",
      "else already made. Here they are yours. Move the qualification bar and",
      "watch the pool, and the story, change."),

  sidebarLayout(
    sidebarPanel(
      width = 3,
      selectInput("season", "Season", choices = c("2026", "2025", "2024"),
                  selected = "2026"),
      sliderInput("mpg", "Qualification: minutes per game the team has played",
                  min = 0, max = 60, value = 30, step = 5),
      sliderInput("min_shots", "Minimum non-penalty shots",
                  min = 0, max = 40, value = 10, step = 1),
      selectInput("yaxis", "Vertical axis",
                  choices = c("Goals" = "np_goals",
                              "Finishing margin (G - npxG)" = "margin",
                              "Placement (xplace)" = "np_xplace")),
      checkboxInput("labels", "Label the extremes", TRUE),
      div(class = "src", textOutput("srcline"))
    ),
    mainPanel(
      width = 9,
      plotOutput("scatter", height = "480px"),
      DTOutput("table")
    )
  )
)

# --------------------------------------------------------------------- server

server <- function(input, output, session) {

  raw <- reactive({ load_players(input$season) })
  output$srcline <- renderText({ paste("Data:", raw()$source) })

  pool <- reactive({
    d <- raw()$data
    d$margin <- d$np_goals - d$npxg
    # The qualification rule from the Python side, per team rather than per
    # league: a club with games in hand is not penalised for it.
    d$bar <- input$mpg * d$team_games
    d[d$minutes >= d$bar & d$np_shots >= input$min_shots, ]
  })

  output$scatter <- renderPlot({
    d <- pool()
    validate(need(nrow(d) > 2, "No players clear these thresholds. Lower the bar."))
    ylab <- names(which(c("np_goals" = "Goals",
                          "margin" = "Finishing margin (G - npxG)",
                          "np_xplace" = "Placement (xplace)")[input$yaxis] ==
                        c("Goals", "Finishing margin (G - npxG)",
                          "Placement (xplace)")))
    d$yv <- d[[input$yaxis]]
    hi <- d[which.max(d$yv), ]

    p <- ggplot(d, aes(npxg, yv)) +
      geom_point(colour = MUTED, size = 2.6, alpha = .75) +
      geom_point(data = hi, colour = AMBER, size = 4.4) +
      labs(
        title = sprintf("%s leads on this measure, of %d players clearing %d min/game",
                        hi$player, nrow(d), input$mpg),
        subtitle = sprintf("Non-penalty. Minimum %d shots. Bars are per team, so a club with games in hand is not penalised.",
                           input$min_shots),
        x = "npxG (season total)",
        y = c("np_goals" = "Goals", "margin" = "Finishing margin (G - npxG)",
              "np_xplace" = "Placement (xplace)")[[input$yaxis]]) +
      theme_minimal(base_size = 13) +
      theme(panel.grid.minor = element_blank(),
            panel.grid.major = element_line(colour = GRID),
            plot.background  = element_rect(fill = PAPER, colour = NA),
            plot.title    = element_text(face = "bold", size = 16, colour = INK),
            plot.subtitle = element_text(colour = "#6b6660", size = 11))

    if (input$yaxis == "margin") p <- p + geom_hline(yintercept = 0, colour = RED, linewidth = .4)
    if (input$labels) {
      ext <- rbind(d[order(-d$yv), ][1:3, ], d[order(d$yv), ][1:2, ])
      p <- p + geom_text(data = ext, aes(label = player), vjust = -1.1,
                         size = 3.4, colour = INK)
    }
    p
  })

  output$table <- renderDT({
    d <- pool()
    d <- d[order(-d$margin), c("player", "team", "position", "minutes",
                               "np_shots", "np_goals", "npxg", "np_xplace", "margin")]
    d$npxg <- round(d$npxg, 2); d$np_xplace <- round(d$np_xplace, 2)
    d$margin <- round(d$margin, 2)
    datatable(d, rownames = FALSE, options = list(pageLength = 10, dom = "tip"),
              colnames = c("Player", "Team", "Pos", "Min", "Shots", "Goals",
                           "npxG", "Placement", "Margin"))
  })
}

shinyApp(ui, server)
