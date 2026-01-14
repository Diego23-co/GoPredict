// ---------- app.js ----------

document.addEventListener("DOMContentLoaded", () => {
    console.log("GoPredict JS loaded");

    // 1️⃣ Mobile menu toggle
    const menuToggle = document.querySelector(".menu-toggle");
    const navMenu = document.querySelector(".nav-menu");

    if (menuToggle && navMenu) {
        menuToggle.addEventListener("click", () => {
            navMenu.classList.toggle("active");
            menuToggle.classList.toggle("open");
        });

        // Close menu when clicking outside
        document.addEventListener("click", (e) => {
            if (!navMenu.contains(e.target) && !menuToggle.contains(e.target)) {
                navMenu.classList.remove("active");
                menuToggle.classList.remove("open");
            }
        });
    }

    // 2️⃣ Smooth scrolling for anchor links
    const scrollLinks = document.querySelectorAll('a[href^="#"]');
    scrollLinks.forEach(link => {
        link.addEventListener("click", (e) => {
            e.preventDefault();
            const target = document.querySelector(link.getAttribute("href"));
            if (target) {
                target.scrollIntoView({ behavior: "smooth", block: "start" });
            }
            // Close menu on mobile after click
            if (navMenu.classList.contains("active")) {
                navMenu.classList.remove("active");
                menuToggle.classList.remove("open");
            }
        });
    });

    // 3️⃣ Contact form UX (disable button while sending)
    const contactForm = document.querySelector(".contact-form");
    if (contactForm) {
        contactForm.addEventListener("submit", (e) => {
            const submitBtn = contactForm.querySelector("button[type='submit']");
            submitBtn.disabled = true;
            submitBtn.textContent = "Sending...";
        });
    }

    // 4️⃣ Optional: detect touch devices for UX tweaks
    const isTouch = "ontouchstart" in window || navigator.maxTouchPoints > 0;
    if (isTouch) {
        document.body.classList.add("touch-device");
    }
});
