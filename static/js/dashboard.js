/* Weekly IN vs OUT: grouped bars, CVD-validated pair (blue IN / orange OUT), 4px rounded ends, 2px gap,
   recessive grid, legend + shared tooltip, and a table view (DESIGN.md). */
(function () {
  const data = JSON.parse(document.getElementById("weeks-data").textContent);
  const el = document.getElementById("chart-weekly");
  new ApexCharts(el, {
    chart: { type: "bar", height: 260, toolbar: { show: false }, fontFamily: "inherit", animations: { enabled: false } },
    series: [{ name: "Stock IN", data: data.map(d => d.in) }, { name: "Stock OUT", data: data.map(d => d.out) }],
    colors: ["#2a78d6", "#eb6834"],
    plotOptions: { bar: { columnWidth: "45%", borderRadius: 4, borderRadiusApplication: "end" } },
    stroke: { show: true, width: 2, colors: ["#ffffff"] },
    dataLabels: { enabled: false },
    grid: { borderColor: "#eef0f3", strokeDashArray: 4 },
    xaxis: { categories: data.map(d => d.label), axisBorder: { show: false }, axisTicks: { show: false } },
    yaxis: { title: { text: "NOS" } },
    legend: { position: "top", horizontalAlign: "left", markers: { shape: "square", size: 7 } },
    tooltip: { shared: true, intersect: false, y: { formatter: v => `${v} NOS` } },
  }).render();
  const table = document.getElementById("chart-table"), btn = document.getElementById("chart-toggle");
  btn.addEventListener("click", () => {
    table.hidden = !table.hidden; el.hidden = !table.hidden;
    btn.innerHTML = table.hidden ? '<i class="ti ti-table"></i> View as table' : '<i class="ti ti-chart-bar"></i> View as chart';
  });
})();
