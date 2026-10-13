/* Outcomes in the last 90 days: one horizontal bar per answer. Words on the axis and a number on every bar,
   so colour is never the only signal (blue = answered well, red = rejected). Table view, as on the stock
   dashboard (DESIGN.md). */
(function () {
  const data = JSON.parse(document.getElementById("outcomes-data").textContent);
  const el = document.getElementById("chart-outcomes");
  new ApexCharts(el, {
    chart: { type: "bar", height: 260, toolbar: { show: false }, fontFamily: "inherit", animations: { enabled: false } },
    series: [{ name: "Pieces", data: data.map(d => d.n) }],
    colors: data.map(d => (d.bad ? "#d63939" : "#1f5fbf")),
    plotOptions: { bar: { horizontal: true, distributed: true, barHeight: "55%", borderRadius: 4, borderRadiusApplication: "end" } },
    dataLabels: { enabled: true, style: { fontSize: "12px" } },
    legend: { show: false },
    grid: { borderColor: "#eef0f3", strokeDashArray: 4 },
    xaxis: { min: 0, tickAmount: Math.min(Math.max(...data.map(d => d.n), 1), 5), categories: data.map(d => d.label), labels: { formatter: v => Math.round(v) }, axisBorder: { show: false }, axisTicks: { show: false } },
    tooltip: { y: { formatter: v => `${v} pieces` } },
  }).render();
  const table = document.getElementById("chart-table"), btn = document.getElementById("chart-toggle");
  btn.addEventListener("click", () => {
    table.hidden = !table.hidden; el.hidden = !table.hidden;
    btn.setAttribute("aria-pressed", String(!table.hidden));
    btn.innerHTML = table.hidden ? '<i class="ti ti-table"></i> View as table' : '<i class="ti ti-chart-bar"></i> View as chart';
  });
})();
