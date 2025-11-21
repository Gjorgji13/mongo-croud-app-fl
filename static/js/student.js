<script>
    window.gradeLabels = [{% for s in subjects %}'{{ s.subject }}',{% endfor %}];
    window.gradeData   = [{% for s in subjects %}{{ s.grade }},{% endfor %}];
</script>


// Prediction fetch (unchanged)
document.getElementById("btnPredict").addEventListener("click", () => {
    fetch(`/predict/${document.getElementById("btnPredict").dataset.student}`)
        .then(r => r.json())
        .then(j => {
            let html = j.prediction === null
                ? `<div class="alert alert-warning">Prediction unavailable. ${j.explanation}</div>`
                : `<div class="alert alert-info"><strong>Predicted grade:</strong> ${j.prediction}<br><small>${j.explanation}</small></div>`;
            document.getElementById("predictionResult").innerHTML = html;
        })
        .catch(() => {
            document.getElementById("predictionResult").innerHTML = `<div class="alert alert-danger">Prediction failed.</div>`;
        });
});


// Chart
window.addEventListener("DOMContentLoaded", () => {
    const ctx = document.getElementById("gradeChart").getContext("2d");

    if (!window.gradeLabels || !window.gradeLabels.length) return;

    new Chart(ctx, {
        type: "bar",
        data: {
            labels: window.gradeLabels,
            datasets: [{
                label: "Grade",
                data: window.gradeData,
                backgroundColor: window.gradeData.map(g => g >= 9 ? "#28a745" : g >= 7 ? "#ffc107" : "#dc2626"),
                borderColor: "#333",
                borderWidth: 1,
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, max: 10 }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(context) { return `Grade: ${context.raw}`; }
                    }
                }
            }
        }
    });
});

// Chart
window.addEventListener("DOMContentLoaded", () => {
    const ctx = document.getElementById("gradeChart").getContext("2d");
    if (!gradeLabels.length) return; // no subjects

    new Chart(ctx, {
        type: "bar",
        data: {
            labels: gradeLabels,
            datasets: [{
                label: "Grade",
                data: gradeData,
                backgroundColor: gradeData.map(g => g >= 9 ? "#28a745" : g >= 7 ? "#ffc107" : "#dc3545"),
                borderColor: "#333",
                borderWidth: 1,
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, max: 10 }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(context) { return `Grade: ${context.raw}`; }
                    }
                }
            }
        }
    });
});


