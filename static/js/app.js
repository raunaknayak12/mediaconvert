/**
 * MediaConvert — Frontend Logic
 */
(function () {
    "use strict";

    var form = document.getElementById("convert-form");
    var urlInput = document.getElementById("url-input");
    var platformBadge = document.getElementById("platform-badge");
    var convertBtn = document.getElementById("convert-btn");
    var formatOptions = document.querySelectorAll(".format-option");

    var progressSection = document.getElementById("progress-section");
    var progressStatus = document.getElementById("progress-status");
    var progressPercent = document.getElementById("progress-percent");
    var progressBarFill = document.getElementById("progress-bar-fill");

    var resultSection = document.getElementById("result-section");
    var resultTitle = document.getElementById("result-title");
    var resultInfo = document.getElementById("result-info");
    var downloadBtn = document.getElementById("download-btn");
    var newConversionBtn = document.getElementById("new-conversion-btn");

    var errorSection = document.getElementById("error-section");
    var errorMessage = document.getElementById("error-message");
    var retryBtn = document.getElementById("retry-btn");

    var historyTbody = document.getElementById("history-tbody");
    var emptyState = document.getElementById("empty-state");
    var refreshHistoryBtn = document.getElementById("refresh-history-btn");
    var toastContainer = document.getElementById("toast-container");

    var currentTaskId = null;
    var pollInterval = null;

    // Platform detection
    function detectPlatform(url) {
        var u = url.toLowerCase();
        if (u.indexOf("youtube.com") !== -1 || u.indexOf("youtu.be") !== -1) return "YouTube";
        if (u.indexOf("instagram.com") !== -1) return "Instagram";
        if (u.indexOf("tiktok.com") !== -1) return "TikTok";
        if (u.indexOf("twitter.com") !== -1 || u.indexOf("x.com") !== -1) return "Twitter/X";
        if (u.indexOf("facebook.com") !== -1 || u.indexOf("fb.watch") !== -1) return "Facebook";
        if (u.indexOf("vimeo.com") !== -1) return "Vimeo";
        if (u.indexOf("soundcloud.com") !== -1) return "SoundCloud";
        return "";
    }

    urlInput.addEventListener("input", function () {
        var platform = detectPlatform(urlInput.value);
        if (platform) {
            platformBadge.textContent = platform + " detected";
            platformBadge.classList.add("visible");
        } else {
            platformBadge.classList.remove("visible");
        }
    });

    // Format selection
    for (var i = 0; i < formatOptions.length; i++) {
        (function (opt) {
            opt.addEventListener("click", function () {
                for (var j = 0; j < formatOptions.length; j++) {
                    formatOptions[j].classList.remove("selected");
                }
                opt.classList.add("selected");
            });
        })(formatOptions[i]);
    }

    // Toast
    function showToast(msg, type) {
        type = type || "info";
        var el = document.createElement("div");
        el.className = "toast toast-" + type;
        el.textContent = msg;
        toastContainer.appendChild(el);
        setTimeout(function () {
            if (el.parentNode) el.parentNode.removeChild(el);
        }, 3500);
    }

    // Reset
    function resetUI() {
        progressSection.classList.add("hidden");
        resultSection.classList.add("hidden");
        errorSection.classList.add("hidden");
        form.classList.remove("hidden");
        convertBtn.disabled = false;
        convertBtn.querySelector(".btn-text").textContent = "Convert";
        progressBarFill.style.width = "0%";
        currentTaskId = null;
        if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
        }
    }

    // Submit
    form.addEventListener("submit", function (e) {
        e.preventDefault();

        var url = urlInput.value.trim();
        var format = document.querySelector('input[name="format"]:checked').value;

        if (!url) {
            showToast("Please enter a URL.", "error");
            return;
        }
        if (url.indexOf("http://") !== 0 && url.indexOf("https://") !== 0) {
            showToast("URL must start with http:// or https://", "error");
            return;
        }

        convertBtn.disabled = true;
        convertBtn.querySelector(".btn-text").textContent = "Starting...";

        fetch("/api/convert", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: url, format: format })
        })
        .then(function (res) { return res.json().then(function (d) { return { ok: res.ok, data: d }; }); })
        .then(function (result) {
            if (!result.ok) throw new Error(result.data.error || "Failed to start.");

            currentTaskId = result.data.task_id;
            showToast("Conversion started!", "success");

            form.classList.add("hidden");
            progressSection.classList.remove("hidden");
            resultSection.classList.add("hidden");
            errorSection.classList.add("hidden");
            progressStatus.textContent = "Starting...";
            progressPercent.textContent = "0%";
            progressBarFill.style.width = "0%";

            pollInterval = setInterval(function () { pollStatus(currentTaskId); }, 1500);
        })
        .catch(function (err) {
            showToast(err.message, "error");
            convertBtn.disabled = false;
            convertBtn.querySelector(".btn-text").textContent = "Convert";
        });
    });

    // Poll
    function pollStatus(taskId) {
        fetch("/api/status/" + taskId)
        .then(function (res) { return res.json(); })
        .then(function (data) {
            var pct = data.progress || "0%";
            var num = parseFloat(pct) || 0;
            progressPercent.textContent = pct;
            progressBarFill.style.width = Math.min(num, 100) + "%";

            if (data.status === "processing") {
                progressStatus.textContent = "Converting...";
            } else if (data.status === "queued") {
                progressStatus.textContent = "Queued...";
            }

            if (data.status === "done") {
                clearInterval(pollInterval);
                pollInterval = null;
                progressBarFill.style.width = "100%";
                progressPercent.textContent = "100%";

                setTimeout(function () {
                    progressSection.classList.add("hidden");
                    resultSection.classList.remove("hidden");
                    resultTitle.textContent = "Done!";
                    var size = data.filesize ? formatBytes(data.filesize) : "Ready";
                    resultInfo.textContent = (data.filename || "media") + " — " + size;
                    loadHistory();
                }, 500);

            } else if (data.status === "error") {
                clearInterval(pollInterval);
                pollInterval = null;
                progressSection.classList.add("hidden");
                errorSection.classList.remove("hidden");
                errorMessage.textContent = data.error || "An unknown error occurred.";
                loadHistory();
            }
        })
        .catch(function (err) {
            console.warn("Poll error:", err.message);
        });
    }

    // Download
    downloadBtn.addEventListener("click", function () {
        if (currentTaskId) {
            window.location.href = "/api/download/" + currentTaskId;
            showToast("Download started!", "success");
        }
    });

    newConversionBtn.addEventListener("click", resetUI);
    retryBtn.addEventListener("click", resetUI);

    // History
    function loadHistory() {
        fetch("/api/history")
        .then(function (res) { return res.json(); })
        .then(function (data) {
            historyTbody.innerHTML = "";

            if (!data.length) {
                emptyState.classList.remove("hidden");
                return;
            }
            emptyState.classList.add("hidden");

            data.forEach(function (item) {
                var tr = document.createElement("tr");

                var actionsHtml = '<div class="action-buttons">';
                actionsHtml += '<button class="btn-action redownload-btn" data-url="' + escapeAttr(item.url) + '" data-format="' + escapeAttr(item.format) + '">Re-Convert</button>';
                actionsHtml += '<button class="btn-action delete delete-btn" data-id="' + escapeAttr(item.task_id) + '">Delete</button>';
                actionsHtml += '</div>';

                tr.innerHTML =
                    '<td class="platform-cell">' + esc(item.platform || "—") + '</td>' +
                    '<td class="url-cell" title="' + escapeAttr(item.url) + '">' + esc(truncate(item.url, 35)) + '</td>' +
                    '<td class="format-cell">' + esc(item.format) + '</td>' +
                    '<td>' + esc(item.filename || "—") + '</td>' +
                    '<td><span class="status-badge ' + item.status + '">' + esc(item.status) + '</span></td>' +
                    '<td>' + formatDate(item.created_at) + '</td>' +
                    '<td>' + actionsHtml + '</td>';

                historyTbody.appendChild(tr);
            });

        })
        .catch(function (err) {
            console.error("Failed to load history:", err);
        });
    }

    refreshHistoryBtn.addEventListener("click", function () {
        loadHistory();
        showToast("History refreshed", "info");
    });

    // Helpers
    function formatBytes(bytes) {
        if (!bytes) return "0 B";
        var k = 1024;
        var sizes = ["B", "KB", "MB", "GB"];
        var i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
    }

    function formatDate(str) {
        if (!str) return "—";
        try {
            var d = new Date(str);
            return d.toLocaleDateString("en-US", {
                month: "short", day: "numeric",
                hour: "2-digit", minute: "2-digit"
            });
        } catch (e) {
            return str;
        }
    }

    function truncate(s, len) {
        if (!s) return "";
        return s.length > len ? s.substring(0, len) + "..." : s;
    }

    function esc(s) {
        if (!s) return "";
        var d = document.createElement("div");
        d.textContent = s;
        return d.innerHTML;
    }

    function escapeAttr(s) {
        if (!s) return "";
        return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "&#39;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    // Event Delegation for History Buttons
    document.addEventListener("click", function(e) {
        // Delete button
        if (e.target && e.target.classList.contains("delete-btn")) {
            if (!confirm("Delete this record?")) return;
            var tid = e.target.getAttribute("data-id");
            fetch("/api/history/" + tid, { method: "DELETE" })
            .then(function (res) {
                if (res.ok) {
                    showToast("Deleted", "success");
                    loadHistory();
                } else {
                    showToast("Failed to delete", "error");
                }
            })
            .catch(function () {
                showToast("Error deleting", "error");
            });
        }
        
        // Re-Convert button
        if (e.target && e.target.classList.contains("redownload-btn")) {
            var url = e.target.getAttribute("data-url");
            var fmt = e.target.getAttribute("data-format");

            resetUI();
            urlInput.value = url;
            urlInput.dispatchEvent(new Event("input"));

            var radioOption = document.getElementById("format-" + fmt);
            if (radioOption) radioOption.checked = true;
            
            for (var m = 0; m < formatOptions.length; m++) {
                formatOptions[m].classList.remove("selected");
            }
            var labelOption = document.getElementById("format-" + fmt + "-label");
            if (labelOption) labelOption.classList.add("selected");

            document.getElementById("converter").scrollIntoView({ behavior: "smooth" });
            
            // Trigger native form submission safely
            setTimeout(function () {
                if (typeof form.requestSubmit === "function") {
                    form.requestSubmit();
                } else {
                    form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
                }
            }, 400);
        }
    });

    // Init
    loadHistory();
})();
