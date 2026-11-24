// Explore page: give feedback while a search is running.
//
// The object page (explore_sub.html) handles the 2D/3D choice and the crochet
// preview itself, with the pattern generated for that object, so nothing for
// it is needed here.

const form = document.getElementById("search-form");
const button = document.getElementById("search-btn");

if (form && button) {
    form.addEventListener("submit", () => {
        button.disabled = true;
        button.textContent = "Searching…";
    });

    // When the user comes back with the browser's Back button, the page can be
    // restored from cache with the button still disabled. Reset it.
    window.addEventListener("pageshow", () => {
        button.disabled = false;
        button.textContent = "Search";
    });
}