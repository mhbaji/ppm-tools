"use strict";

window.chooseExportSheetMode = function chooseExportSheetMode() {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.className = "export-choice-dialog";
    dialog.setAttribute("aria-labelledby", "export-choice-title");

    const heading = document.createElement("h2");
    heading.id = "export-choice-title";
    heading.textContent = "Unduh laporan Excel";
    const description = document.createElement("p");
    description.textContent = "Pilih bagaimana laporan disusun.";

    const actions = document.createElement("div");
    actions.className = "export-choice-actions";
    const addAction = (label, mode, className) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = className;
      button.textContent = label;
      button.addEventListener("click", () => dialog.close(mode));
      actions.append(button);
    };
    addAction("Satu sheet", "single", "button button-secondary");
    addAction("Sheet per Sub Unit", "sub_unit", "button button-primary");

    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "export-choice-cancel";
    cancel.textContent = "Batal";
    cancel.addEventListener("click", () => dialog.close(""));

    dialog.append(heading, description, actions, cancel);
    document.body.append(dialog);
    dialog.addEventListener("close", () => {
      const mode = dialog.returnValue || null;
      dialog.remove();
      resolve(mode);
    }, { once: true });
    dialog.showModal();
  });
};
