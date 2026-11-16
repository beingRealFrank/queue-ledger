window.goatcounter = {endpoint: "https://queueledger.goatcounter.com/count"};
(function () { var s = document.createElement("script"); s.async = true; s.src = "https://gc.zgo.at/count.js"; document.head.appendChild(s); })();
document.addEventListener("click", function (ev) {
  var a = ev.target.closest && ev.target.closest("a[href]");
  if (!a || !window.goatcounter || !window.goatcounter.count) return;
  var h = a.getAttribute("href") || "";
  var ev2 = /\.csv$/.test(h) ? "download-csv" : /buy\.polar\.sh/.test(h) ? "pro-checkout-click" : /apify\.com/.test(h) ? "apify-click" : "";
  if (ev2) window.goatcounter.count({path: ev2 + ":" + h.split("/").pop().slice(0, 40), title: ev2, event: true});
});
