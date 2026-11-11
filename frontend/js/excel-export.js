"use strict";

window.downloadXlsx = function downloadXlsx(filename, sheets) {
  const encoder = new TextEncoder();
  const files = [];
  const xmlEscape = (value) => String(value ?? "")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, "")
    .replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&apos;",
    })[character]);
  const columnName = (column) => {
    let name = "";
    while (column > 0) {
      const remainder = (column - 1) % 26;
      name = String.fromCharCode(65 + remainder) + name;
      column = Math.floor((column - 1) / 26);
    }
    return name;
  };
  const safeSheetName = (name, index, used) => {
    let title = String(name || `Sheet ${index + 1}`)
      .replace(/[\\/*?:[\]]/g, " ")
      .trim()
      .slice(0, 31) || `Sheet ${index + 1}`;
    const base = title;
    let suffix = 1;
    while (used.has(title.toLowerCase())) {
      const tail = ` ${suffix++}`;
      title = `${base.slice(0, 31 - tail.length)}${tail}`;
    }
    used.add(title.toLowerCase());
    return title;
  };
  const crc32 = (bytes) => {
    let crc = 0xffffffff;
    for (const byte of bytes) {
      crc ^= byte;
      for (let bit = 0; bit < 8; bit += 1) {
        crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
      }
    }
    return (crc ^ 0xffffffff) >>> 0;
  };
  const uint16 = (value) => {
    const bytes = new Uint8Array(2);
    new DataView(bytes.buffer).setUint16(0, value, true);
    return bytes;
  };
  const uint32 = (value) => {
    const bytes = new Uint8Array(4);
    new DataView(bytes.buffer).setUint32(0, value >>> 0, true);
    return bytes;
  };
  const concat = (parts) => {
    const size = parts.reduce((total, part) => total + part.length, 0);
    const result = new Uint8Array(size);
    let offset = 0;
    for (const part of parts) {
      result.set(part, offset);
      offset += part.length;
    }
    return result;
  };

  const usedNames = new Set();
  const workbookSheets = sheets.map((sheet, index) => ({
    name: safeSheetName(sheet.name, index, usedNames),
    rows: sheet.rows,
  }));
  const workbookRelationships = workbookSheets.map(
    (_, index) => `<Relationship Id="rId${index + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${index + 1}.xml"/>`,
  ).join("");
  const contentOverrides = workbookSheets.map(
    (_, index) => `<Override PartName="/xl/worksheets/sheet${index + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`,
  ).join("");

  files.push(
    ["[Content_Types].xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>${contentOverrides}</Types>`],
    ["_rels/.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`],
    ["xl/workbook.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>${workbookSheets.map((sheet, index) => `<sheet name="${xmlEscape(sheet.name)}" sheetId="${index + 1}" r:id="rId${index + 1}"/>`).join("")}</sheets></workbook>`],
    ["xl/_rels/workbook.xml.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${workbookRelationships}</Relationships>`],
  );
  workbookSheets.forEach((sheet, sheetIndex) => {
    const rows = sheet.rows.map((row, rowIndex) => {
      const cells = row.map((value, columnIndex) => {
        if (value === null || value === undefined || value === "") return "";
        const cellRef = `${columnName(columnIndex + 1)}${rowIndex + 1}`;
        if (typeof value === "number" && Number.isFinite(value)) {
          return `<c r="${cellRef}" t="n"><v>${value}</v></c>`;
        }
        return `<c r="${cellRef}" t="inlineStr"><is><t xml:space="preserve">${xmlEscape(value)}</t></is></c>`;
      }).join("");
      return `<row r="${rowIndex + 1}">${cells}</row>`;
    }).join("");
    files.push([
      `xl/worksheets/sheet${sheetIndex + 1}.xml`,
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${rows}</sheetData></worksheet>`,
    ]);
  });

  const localRecords = [];
  const centralRecords = [];
  let localOffset = 0;
  for (const [name, content] of files) {
    const nameBytes = encoder.encode(name);
    const dataBytes = encoder.encode(content);
    const checksum = crc32(dataBytes);
    const localHeader = concat([
      uint32(0x04034b50), uint16(20), uint16(0), uint16(0), uint16(0), uint16(0),
      uint32(checksum), uint32(dataBytes.length), uint32(dataBytes.length),
      uint16(nameBytes.length), uint16(0), nameBytes,
    ]);
    localRecords.push(localHeader, dataBytes);
    const centralHeader = concat([
      uint32(0x02014b50), uint16(20), uint16(20), uint16(0), uint16(0), uint16(0),
      uint16(0), uint32(checksum), uint32(dataBytes.length), uint32(dataBytes.length),
      uint16(nameBytes.length), uint16(0), uint16(0), uint16(0), uint16(0),
      uint32(0), uint32(localOffset), nameBytes,
    ]);
    centralRecords.push(centralHeader);
    localOffset += localHeader.length + dataBytes.length;
  }
  const centralDirectory = concat(centralRecords);
  const endRecord = concat([
    uint32(0x06054b50), uint16(0), uint16(0), uint16(files.length),
    uint16(files.length), uint32(centralDirectory.length), uint32(localOffset),
    uint16(0),
  ]);
  const workbook = concat([...localRecords, centralDirectory, endRecord]);
  const blobUrl = URL.createObjectURL(new Blob([workbook], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  }));
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
};
