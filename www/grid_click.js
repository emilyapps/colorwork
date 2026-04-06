// grid_click.js — delegated click handler for the SVG pattern grid.
// Reads data-row / data-col / data-region from the clicked .grid-cell element
// and sends the coordinates to Shiny as input.cell_click.
//
// The nonce field forces Shiny to treat every click as a new event, even when
// the same cell is clicked twice in a row (without it, identical values are
// deduplicated and the second click is silently dropped).

document.addEventListener("click", function (e) {
    const cell = e.target.closest(".grid-cell");
    if (!cell) return;
    Shiny.setInputValue(
        "cell_click",
        {
            row:    parseInt(cell.dataset.row,    10),
            col:    parseInt(cell.dataset.col,    10),
            region: cell.dataset.region,
            nonce:  Math.random(),
        },
        { priority: "event" }
    );
});
