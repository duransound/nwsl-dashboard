"""
Plain-language glossary for the Methods & Data tab.

Why this is separate from the Methods tab's own sections: those sections
answer an analyst's question — which model, which endpoints, what τ² came out
at. This one answers a reader's question, which is "what is xG." Both belong
on the same tab, but they're written for different people and mixing them
produces prose that serves neither.

It's a section in `chart_builders.build_methods_chart`'s shape
({"heading": ..., "items": [{"term", "detail"}]}), so it renders through the
existing `drawMethods()` with no template change, and `build_dashboard.py`
inserts it at position 0 so the tab opens with the vocabulary and then gets
progressively more technical.

Voice follows the project's Design Guidelines: lead with the point, plain
sentences, no jargon used to explain jargon. Every entry answers "so what" in
its first sentence and only then adds the nuance.
"""

GLOSSARY_SECTION = {
    "heading": "Start here: what the words mean",
    "items": [
        {
            "term": "Expected goals (xG)",
            "detail": (
                "A number between 0 and 1 for every shot: how often a chance like that one gets "
                "scored. A tap-in might be 0.7, a hopeful strike from 30 yards 0.03. Add up a "
                "team's shots and you get the goals an average finisher would have scored from "
                "the chances they made. It measures chances, not finishing — two teams with the "
                "same xG created equally good openings, and what they did with them is the "
                "separate question the Goals vs. xG tab is about."),
        },
        {
            "term": "Expected assists (xA)",
            "detail": (
                "The same idea applied to the pass before the shot: what the chances a player set "
                "up were worth, whether or not the shooter finished them. It's the cleanest way "
                "to separate a creator from her teammates' finishing — a playmaker on a cold team "
                "has a low assist count and an unchanged xA."),
        },
        {
            "term": "xG differential (xGF − xGA)",
            "detail": (
                "Chances created minus chances conceded, across the season. The simplest "
                "one-number answer to whether a team is out-chancing its opponents or being "
                "out-chanced, and it tends to describe the rest of a season better than goal "
                "difference does, because it's less hostage to a handful of unusually good or "
                "unusually wasteful finishing days."),
        },
        {
            "term": "Goals added (g+)",
            "detail": (
                "An attempt to value everything a player does on the ball, not just shots and "
                "assists. Every touch — a pass, a carry, a take-on, an interception — is scored "
                "by how much it moved her team's chance of scoring up or down. Added up, that's "
                "roughly how many goals of value she contributed. It's the metric doing the most "
                "work on this dashboard; the technical definition is under “What the derived "
                "quantities mean” below."),
        },
        {
            "term": "Per 96 minutes",
            "detail": (
                "A rate rather than a total. Ninety-six minutes is about one full match including "
                "stoppage time, so “g+ per 96” means “value contributed per match "
                "played.” It's what lets a substitute with 400 minutes be compared to a "
                "starter with 1,800 without the starter winning on volume alone."),
        },
        {
            "term": "Above replacement",
            "detail": (
                "Replacement level is the baseline: what a freely available roster-filler would "
                "give you at that position. A player at +0.05 g+ per 96 above replacement is that "
                "much better than the easiest alternative available. The bar is deliberately not "
                "“average” — for a squad-building decision the real question isn't "
                "whether a starter is above average, it's whether she's worth more than the next "
                "player up. Note these are per-match rates, so gaps look small: 0.05 per 96 is "
                "about 1.2 goals across a full season of starts."),
        },
        {
            "term": "The colours",
            "detail": (
                "Amber marks the point of the chart — the team or player the headline is about. "
                "Red marks a value below the baseline. Grey is context: everyone else, there so "
                "you can see whether the highlighted mark is unusual. The colours never change "
                "meaning between tabs."),
        },
        {
            "term": "What none of this can tell you",
            "detail": (
                "These numbers describe what happened, not why — xG doesn't know a defender "
                "slipped, or that a team spent an hour chasing a two-goal deficit. Season-to-date "
                "means small samples early, so a figure in April is a far weaker signal than the "
                "same one in September. And every goals-added figure is one model's estimate, not "
                "a measured fact. It's useful for deciding where to look, not for deciding what "
                "to think."),
        },
    ],
}
