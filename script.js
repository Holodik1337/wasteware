// Плавная прокрутка
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Анимация появления элементов при скролле
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -100px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
        }
    });
}, observerOptions);

// Применяем анимацию к карточкам услуг
document.querySelectorAll('.service-card').forEach(card => {
    card.style.opacity = '0';
    card.style.transform = 'translateY(50px)';
    card.style.transition = 'all 0.6s ease-out';
    observer.observe(card);
});

// Эффект параллакса для фона
window.addEventListener('scroll', () => {
    const scrolled = window.pageYOffset;
    const parallax = document.querySelector('.particles');
    if (parallax) {
        parallax.style.transform = `translateY(${scrolled * 0.5}px)`;
    }
});

// Изменение навбара при скролле
window.addEventListener('scroll', () => {
    const navbar = document.querySelector('.navbar');
    if (window.scrollY > 100) {
        navbar.style.background = 'rgba(10, 10, 15, 0.98)';
        navbar.style.boxShadow = '0 5px 20px rgba(0, 243, 255, 0.1)';
    } else {
        navbar.style.background = 'rgba(10, 10, 15, 0.95)';
        navbar.style.boxShadow = 'none';
    }
});

// Создание анимированных частиц
function createParticles() {
    const particlesContainer = document.querySelector('.particles');
    if (!particlesContainer) return;

    for (let i = 0; i < 50; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';
        particle.style.cssText = `
            position: absolute;
            width: 2px;
            height: 2px;
            background: ${i % 2 === 0 ? 'var(--neon-blue)' : 'var(--neon-pink)'};
            border-radius: 50%;
            left: ${Math.random() * 100}%;
            top: ${Math.random() * 100}%;
            opacity: ${Math.random() * 0.5 + 0.2};
            animation: twinkle ${Math.random() * 3 + 2}s infinite;
        `;
        particlesContainer.appendChild(particle);
    }
}

// CSS для анимации мерцания
const style = document.createElement('style');
style.textContent = `
    @keyframes twinkle {
        0%, 100% { opacity: 0.2; transform: scale(1); }
        50% { opacity: 1; transform: scale(1.5); }
    }
`;
document.head.appendChild(style);

// Запуск создания частиц
createParticles();

// Курсор с эффектом свечения
document.addEventListener('mousemove', (e) => {
    const cursor = document.createElement('div');
    cursor.style.cssText = `
        position: fixed;
        width: 20px;
        height: 20px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(0,243,255,0.3) 0%, transparent 70%);
        pointer-events: none;
        left: ${e.clientX - 10}px;
        top: ${e.clientY - 10}px;
        z-index: 9999;
        animation: cursorFade 1s forwards;
    `;
    document.body.appendChild(cursor);
    
    setTimeout(() => cursor.remove(), 1000);
});

const cursorStyle = document.createElement('style');
cursorStyle.textContent = `
    @keyframes cursorFade {
        to { opacity: 0; transform: scale(2); }
    }
`;
document.head.appendChild(cursorStyle);

console.log('🎥 Edit Studio Website Loaded');
