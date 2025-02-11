document.addEventListener("DOMContentLoaded", function () {
    const navIcon = document.getElementById("nav-icon");
    const navbarNav = document.querySelector(".navbar-collapse");

    navIcon.addEventListener("click", function () {
        this.classList.toggle("open");
        navbarNav.classList.toggle("open");
    });
});
document.addEventListener("DOMContentLoaded", function () {
    window.addEventListener("scroll", function () {
        const header = document.querySelector("header");
        if (window.scrollY > 50) { // Adjust the scroll threshold as needed
            header.classList.add("scrolled");
        } else {
            header.classList.remove("scrolled");
        }
    });
});
document.addEventListener("DOMContentLoaded", function() {
    const header = document.querySelector("header");
    const logo = document.querySelector(".navbar-brand img");
    
    // Get static paths from data- attributes
    const originalLogo = logo.getAttribute("data-original-logo");
    const scrolledLogo = logo.getAttribute("data-scrolled-logo");
    
    let isLogoChanged = false; // Flag to track if the logo has already been changed

    window.addEventListener("scroll", function() {
        if (window.scrollY > 50 && !isLogoChanged) { // When scrolled and logo not changed
            header.classList.add("scrolled");
            logo.src = scrolledLogo; // Change logo source
            isLogoChanged = true; // Set flag to prevent further changes
        } else if (window.scrollY <= 50 && isLogoChanged) { // When scrolled back to top and logo has been changed
            header.classList.remove("scrolled");
            logo.src = originalLogo; // Reset to original logo
            isLogoChanged = false; // Reset flag
        }
    });
});