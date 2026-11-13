// giving feedback while a search is running.
const form = document.getElementById("search-form");
const button = document.getElementById("search-btn");
 
if (form && button) {
    form.addEventListener("submit", () => {
        button.disabled = true;
        button.textContent = "Searching…";
    });
}
 
// choosing btw 2D and 3D crochet.
const options = document.querySelectorAll(".style-option");
const styleLabel = document.getElementById("style-label");
 
options.forEach((option) => {
    option.addEventListener("click", () => {
        options.forEach((o) => (o.style.border = ""));
        option.style.border = "2px solid var(--text-dark)";
        styleLabel.textContent = "(" + option.dataset.style + ")";
    });
});