// 1) Explore page: give feedback while a search is running.
const form = document.getElementById("search-form");
const button = document.getElementById("search-btn");

if (form && button) {
    form.addEventListener("submit", () => {
        button.disabled = true;
        button.textContent = "Searching…";
    });
}

// 2) Object page: choose between 2D and 3D crochet.
const options = document.querySelectorAll(".style-option");
const styleLabel = document.getElementById("style-label");
const viewerSection = document.getElementById("viewer-section");
const viewerBox = document.getElementById("viewer");
const viewerStatus = document.getElementById("viewer-status");

// TODO backend: replace this sample with the generated pattern for the object.
function getPattern() {
    return [
        "ring",
        "6 sc",
        "6 inc",
        "6*(sc,inc)",
        "18 sc",
        "18 sc",
        "18 sc",
        "6*(sc,dec)",
        "6 dec",
    ].join("\n");
}

let viewer = null; // created the first time the user picks 3D

function showViewer() {
    viewerSection.classList.remove("d-none");

    if (typeof CrochetViewer === "undefined") {
        viewerStatus.textContent =
            "The 3D viewer could not be loaded. Check your internet connection and reload the page.";
        return;
    }

    if (!viewer) {
        viewer = CrochetViewer.mount(viewerBox, {
            mode: "yarn",
            thickness: 0.27,
            iterations: 400,
            onError: (message) => {
                viewerStatus.textContent = message || "";
            },
            onStatus: (s) => {
                viewerStatus.textContent = s.done
                    ? s.rows + " rows · " + s.stitches + " stitches"
                    : "Shaping the yarn… " + s.iteration + "/" + s.iterations;
            },
        });
        viewer.setPattern(getPattern());
    }

    viewerSection.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function hideViewer() {
    if (viewerSection) viewerSection.classList.add("d-none");
}

options.forEach((option) => {
    option.addEventListener("click", () => {
        options.forEach((o) => (o.style.border = ""));
        option.style.border = "2px solid var(--text-dark)";
        styleLabel.textContent = "(" + option.dataset.style + ")";

        if (option.dataset.style === "3D") {
            showViewer();
        } else {
            hideViewer();
        }
    });
});