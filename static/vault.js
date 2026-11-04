/* =====================================================
   ISHWAR PRIVATE VAULT
   Local encrypted photo and video storage
   AES-GCM 256-bit + PBKDF2 SHA-256
===================================================== */

(() => {
  "use strict";

  const DB_NAME = "ishwar_private_vault_v1";
  const DB_VERSION = 1;
  const META_STORE = "meta";
  const FILE_STORE = "files";

  const PBKDF2_ITERATIONS = 310000;
  const MAX_FILE_SIZE = 50 * 1024 * 1024;
  const AUTO_LOCK_TIME = 5 * 60 * 1000;
  const CHECK_TEXT = "ISHWAR_PRIVATE_VAULT_OK";

  let db = null;
  let vaultKey = null;
  let autoLockTimer = null;
  let objectUrls = [];

  const $ = id => document.getElementById(id);

  /* -----------------------------
     MESSAGE
  ----------------------------- */

  function showMessage(message, isError = false) {
    let box = $("vaultMessage");

    if (!box) {
      box = document.createElement("p");
      box.id = "vaultMessage";
      box.setAttribute("aria-live", "polite");

      box.style.padding = "12px";
      box.style.margin = "12px 0";
      box.style.borderRadius = "8px";

      const panel = $("vaultPanel");

      if (panel) {
        const intro = panel.querySelector("p");

        if (intro) {
          intro.insertAdjacentElement("afterend", box);
        } else {
          panel.prepend(box);
        }
      }
    }

    box.textContent = message;
    box.style.color = isError ? "#ff8585" : "#70e6b2";
    box.style.background = isError ? "#401c25" : "#12352b";
  }

  function setVaultStatus(message, isError = false) {
    const status = $("vaultStatus");

    if (status) {
      status.textContent = message;
      status.style.color = isError ? "#ff8585" : "";
    } else {
      showMessage(message, isError);
    }
  }

  /* -----------------------------
     HELPERS
  ----------------------------- */

  function randomBytes(length) {
    const bytes = new Uint8Array(length);
    crypto.getRandomValues(bytes);
    return bytes;
  }

  function makeId() {
    if (crypto.randomUUID) {
      return crypto.randomUUID();
    }

    return Array.from(randomBytes(16))
      .map(byte => byte.toString(16).padStart(2, "0"))
      .join("");
  }

  function isValidPin(pin) {
    return /^\d{6}$/.test(pin);
  }

  function cleanPinInput(input) {
    input.value = input.value
      .replace(/\D/g, "")
      .slice(0, 6);
  }

  /* -----------------------------
     INDEXED DB
  ----------------------------- */

  function openDatabase() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onupgradeneeded = () => {
        const database = request.result;

        if (!database.objectStoreNames.contains(META_STORE)) {
          database.createObjectStore(META_STORE, {
            keyPath: "id"
          });
        }

        if (!database.objectStoreNames.contains(FILE_STORE)) {
          database.createObjectStore(FILE_STORE, {
            keyPath: "id"
          });
        }
      };

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
      request.onblocked = () => {
        reject(new Error("Vault database is blocked."));
      };
    });
  }

  function getRecord(storeName, id) {
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(storeName, "readonly");
      const request = transaction.objectStore(storeName).get(id);

      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
  }

  function getAllRecords(storeName) {
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(storeName, "readonly");
      const request = transaction.objectStore(storeName).getAll();

      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => reject(request.error);
    });
  }

  function saveRecord(storeName, record) {
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(storeName, "readwrite");

      transaction.objectStore(storeName).put(record);

      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  }

  function deleteRecord(storeName, id) {
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(storeName, "readwrite");

      transaction.objectStore(storeName).delete(id);

      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  }

  /* -----------------------------
     ENCRYPTION
  ----------------------------- */

  async function deriveKey(pin, salt) {
    const pinKey = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(pin),
      "PBKDF2",
      false,
      ["deriveKey"]
    );

    return crypto.subtle.deriveKey(
      {
        name: "PBKDF2",
        salt,
        iterations: PBKDF2_ITERATIONS,
        hash: "SHA-256"
      },
      pinKey,
      {
        name: "AES-GCM",
        length: 256
      },
      false,
      ["encrypt", "decrypt"]
    );
  }

  async function encryptBytes(bytes, key) {
    const iv = randomBytes(12);

    const encrypted = await crypto.subtle.encrypt(
      {
        name: "AES-GCM",
        iv
      },
      key,
      bytes
    );

    return {
      iv: iv.buffer,
      data: encrypted
    };
  }

  async function decryptBytes(data, iv, key) {
    return crypto.subtle.decrypt(
      {
        name: "AES-GCM",
        iv: new Uint8Array(iv)
      },
      key,
      data
    );
  }

  /* -----------------------------
     CREATE VAULT
  ----------------------------- */

  async function createVault() {
    const pin = $("vaultNewPin")?.value || "";
    const confirmPin = $("vaultConfirmPin")?.value || "";

    if (!isValidPin(pin)) {
      showMessage("PIN ठीक 6 अंकों का होना चाहिए।", true);
      return;
    }

    if (pin !== confirmPin) {
      showMessage("दोनों PIN एक जैसे नहीं हैं।", true);
      return;
    }

    const button = $("vaultCreateBtn");
    if (button) button.disabled = true;

    try {
      const existing = await getRecord(META_STORE, "vault");

      if (existing) {
        showMessage("Vault पहले से बना हुआ है। Unlock करें।", true);
        await refreshVaultScreen();
        return;
      }

      const salt = randomBytes(16);
      const key = await deriveKey(pin, salt);
      const checkIv = randomBytes(12);

      const checkData = await crypto.subtle.encrypt(
        {
          name: "AES-GCM",
          iv: checkIv
        },
        key,
        new TextEncoder().encode(CHECK_TEXT)
      );

      await saveRecord(META_STORE, {
        id: "vault",
        salt: salt.buffer,
        checkIv: checkIv.buffer,
        checkData
      });

      vaultKey = key;

      $("vaultNewPin").value = "";
      $("vaultConfirmPin").value = "";

      showMessage("आपका Private Vault बन गया है।");

      await showUnlockedVault();

    } catch (error) {
      console.error("Vault creation error:", error);

      showMessage(
        "Vault नहीं बन पाया। ब्राउज़र स्टोरेज जाँचें।",
        true
      );
    } finally {
      if (button) button.disabled = false;
    }
  }

  /* -----------------------------
     UNLOCK VAULT
  ----------------------------- */

  async function unlockVault() {
    const pin = $("vaultPin")?.value || "";

    if (!isValidPin(pin)) {
      showMessage("अपना 6 अंकों का PIN डालें।", true);
      return;
    }

    const button = $("vaultUnlockBtn");
    if (button) button.disabled = true;

    try {
      const meta = await getRecord(META_STORE, "vault");

      if (!meta) {
        showMessage("Vault नहीं मिला। पहले Vault बनाएँ।", true);
        await refreshVaultScreen();
        return;
      }

      const key = await deriveKey(
        pin,
        new Uint8Array(meta.salt)
      );

      const decrypted = await decryptBytes(
        meta.checkData,
        meta.checkIv,
        key
      );

      const checkText = new TextDecoder().decode(decrypted);

      if (checkText !== CHECK_TEXT) {
        throw new Error("Incorrect PIN");
      }

      vaultKey = key;
      $("vaultPin").value = "";

      showMessage("Vault सफलतापूर्वक Unlock हो गया।");

      await showUnlockedVault();

    } catch (error) {
      console.error("Vault unlock error:", error);

      showMessage("गलत PIN या Vault डेटा पढ़ने में समस्या।", true);
    } finally {
      if (button) button.disabled = false;
    }
  }

  /* -----------------------------
     PACK FILE
     Metadata is also encrypted.
  ----------------------------- */

  async function packFile(file) {
    const metadata = {
      name: file.name,
      type: file.type,
      size: file.size,
      createdAt: Date.now()
    };

    const metadataBytes = new TextEncoder().encode(
      JSON.stringify(metadata)
    );

    const fileBytes = new Uint8Array(
      await file.arrayBuffer()
    );

    const packed = new Uint8Array(
      4 + metadataBytes.length + fileBytes.length
    );

    new DataView(packed.buffer).setUint32(
      0,
      metadataBytes.length
    );

    packed.set(metadataBytes, 4);
    packed.set(fileBytes, 4 + metadataBytes.length);

    return packed;
  }

  async function unpackFile(encryptedData, iv) {
    const decrypted = await decryptBytes(
      encryptedData,
      iv,
      vaultKey
    );

    const bytes = new Uint8Array(decrypted);

    if (bytes.length < 4) {
      throw new Error("Invalid file data");
    }

    const metadataLength = new DataView(
      bytes.buffer
    ).getUint32(0);

    if (metadataLength > bytes.length - 4) {
      throw new Error("Invalid metadata");
    }

    const metadataBytes = bytes.slice(
      4,
      4 + metadataLength
    );

    const fileBytes = bytes.slice(
      4 + metadataLength
    );

    const metadata = JSON.parse(
      new TextDecoder().decode(metadataBytes)
    );

    return {
      metadata,
      blob: new Blob([fileBytes], {
        type: metadata.type || "application/octet-stream"
      })
    };
  }

  /* -----------------------------
     ADD FILES
  ----------------------------- */

  async function addFiles(fileList) {
    if (!vaultKey) {
      showMessage("पहले Vault Unlock करें।", true);
      return;
    }

    const files = Array.from(fileList || []);

    if (!files.length) return;

    for (const file of files) {
      if (
        !file.type.startsWith("image/") &&
        !file.type.startsWith("video/")
      ) {
        setVaultStatus(
          `${file.name}: केवल फोटो और वीडियो जोड़ सकते हैं।`,
          true
        );
        continue;
      }

      if (file.size > MAX_FILE_SIZE) {
        setVaultStatus(
          `${file.name}: फाइल 50 MB से बड़ी है।`,
          true
        );
        continue;
      }

      try {
        setVaultStatus(`${file.name} सुरक्षित की जा रही है...`);

        const packed = await packFile(file);
        const encrypted = await encryptBytes(packed, vaultKey);

        await saveRecord(FILE_STORE, {
          id: makeId(),
          iv: encrypted.iv,
          data: encrypted.data
        });

      } catch (error) {
        console.error("File save error:", error);

        if (error.name === "QuotaExceededError") {
          setVaultStatus(
            "ब्राउज़र स्टोरेज भर गई है।",
            true
          );
        } else {
          setVaultStatus(
            `${file.name} सेव नहीं हो पाई।`,
            true
          );
        }
      }
    }

    await loadGallery();
    setVaultStatus("फाइल जोड़ने का काम पूरा हुआ।");
    resetAutoLockTimer();
  }

  /* -----------------------------
     GALLERY
  ----------------------------- */

  function clearGallery() {
    objectUrls.forEach(url => URL.revokeObjectURL(url));
    objectUrls = [];

    const gallery = $("vaultGallery");

    if (gallery) gallery.replaceChildren();
  }

  function formatFileSize(bytes) {
    const size = Number(bytes) || 0;

    if (size < 1024) return size + " Bytes";

    if (size < 1024 * 1024) {
      return (size / 1024).toFixed(1) + " KB";
    }

    return (size / (1024 * 1024)).toFixed(2) + " MB";
  }

  async function loadGallery() {
    if (!vaultKey) return;

    const gallery = $("vaultGallery");
    if (!gallery) return;

    clearGallery();

    const records = await getAllRecords(FILE_STORE);

    if (!records.length) {
      const empty = document.createElement("div");

      empty.className = "vault-empty";
      empty.textContent =
        "अभी Vault में कोई फोटो या वीडियो नहीं है।";

      gallery.appendChild(empty);
      return;
    }

    for (const record of records) {
      if (!vaultKey) return;

      try {
        const result = await unpackFile(
          record.data,
          record.iv
        );

        if (!vaultKey) return;

        const url = URL.createObjectURL(result.blob);
        objectUrls.push(url);

        const item = document.createElement("div");
        item.className = "vault-item";

        let media;

        if (result.metadata.type.startsWith("video/")) {
          media = document.createElement("video");
          media.controls = true;
          media.preload = "metadata";
        } else {
          media = document.createElement("img");
          media.alt = result.metadata.name || "Private photo";
          media.loading = "lazy";
        }

        media.src = url;

        const info = document.createElement("div");
        info.className = "vault-item-info";

        const name = document.createElement("strong");
        name.textContent = result.metadata.name || "Private file";

        const size = document.createElement("small");
        size.textContent = formatFileSize(result.metadata.size);

        const deleteButton = document.createElement("button");

        deleteButton.type = "button";
        deleteButton.className = "vault-delete-button";
        deleteButton.textContent = "🗑️ Delete";

        deleteButton.addEventListener("click", async () => {
          if (!window.confirm("क्या इस फाइल को डिलीट करना चाहते हैं?")) {
            return;
          }

          try {
            await deleteRecord(FILE_STORE, record.id);
            await loadGallery();

            setVaultStatus("फाइल डिलीट कर दी गई है।");
            resetAutoLockTimer();

          } catch (error) {
            console.error(error);
            setVaultStatus("फाइल डिलीट नहीं हो पाई।", true);
          }
        });

        info.append(name, size, deleteButton);
        item.append(media, info);
        gallery.appendChild(item);

      } catch (error) {
        console.error("File decryption error:", error);

        const errorItem = document.createElement("div");

        errorItem.className = "vault-empty";
        errorItem.textContent =
          "एक फाइल पढ़ी नहीं जा सकी।";

        gallery.appendChild(errorItem);
      }
    }
  }

  /* -----------------------------
     SHOW / LOCK
  ----------------------------- */

  async function showUnlockedVault() {
    $("vaultSetup").hidden = true;
    $("vaultUnlock").hidden = true;
    $("vaultContent").hidden = false;

    await loadGallery();
    resetAutoLockTimer();
  }

  function lockVault() {
    clearTimeout(autoLockTimer);
    autoLockTimer = null;

    clearGallery();
    vaultKey = null;

    $("vaultContent").hidden = true;

    refreshVaultScreen();

    showMessage("Vault Lock कर दिया गया है।");
  }

  async function refreshVaultScreen() {
    try {
      const meta = await getRecord(META_STORE, "vault");

      $("vaultSetup").hidden = !!meta;
      $("vaultUnlock").hidden = !meta;
      $("vaultContent").hidden = true;

    } catch (error) {
      console.error(error);
      showMessage("Vault की जानकारी पढ़ने में समस्या हुई।", true);
    }
  }

  /* -----------------------------
     AUTO LOCK
  ----------------------------- */

  function resetAutoLockTimer() {
    clearTimeout(autoLockTimer);

    if (!vaultKey) return;

    autoLockTimer = setTimeout(() => {
      lockVault();
    }, AUTO_LOCK_TIME);
  }

  function setupActivityTracking() {
    ["click", "keydown", "touchstart"].forEach(eventName => {
      document.addEventListener(eventName, () => {
        if (vaultKey) resetAutoLockTimer();
      }, { passive: true });
    });

    document.addEventListener("visibilitychange", () => {
      if (document.hidden && vaultKey) {
        lockVault();
      }
    });

    window.addEventListener("pagehide", () => {
      if (vaultKey) lockVault();
    });
  }

  /* -----------------------------
     FILE PICKER BUTTON
  ----------------------------- */

  function setupFilePicker() {
    const fileInput = $("vaultFiles");
    const chooseButton = $("vaultChooseFilesBtn");

    if (!fileInput) {
      showMessage("फोटो चुनने वाला input नहीं मिला।", true);
      return;
    }

    // Button मौजूद है तो उससे file picker खोलें।
    if (chooseButton) {
      chooseButton.addEventListener("click", event => {
        event.preventDefault();
        fileInput.click();
      });
    }

    // पुराना label भी हो तो वह native तरीके से काम करेगा।
    fileInput.addEventListener("change", async event => {
      const selectedFiles = event.target.files;

      if (selectedFiles && selectedFiles.length) {
        await addFiles(selectedFiles);
      }

      // Same file दोबारा चुनने के लिए input reset करें।
      fileInput.value = "";
    });
  }

  /* -----------------------------
     INITIALIZE
  ----------------------------- */

  async function initVault() {
    const requiredElements = [
      "vaultPanel",
      "vaultSetup",
      "vaultUnlock",
      "vaultContent",
      "vaultCreateBtn",
      "vaultUnlockBtn",
      "vaultLockBtn",
      "vaultFiles",
      "vaultGallery"
    ];

    const missing = requiredElements.filter(id => !$(id));

    if (missing.length) {
      console.error("Vault HTML elements missing:", missing);
      return;
    }

    if (!window.isSecureContext || !crypto?.subtle) {
      showMessage(
        "Vault के लिए HTTPS और Web Crypto सपोर्ट जरूरी है।",
        true
      );
      return;
    }

    if (!window.indexedDB) {
      showMessage(
        "यह ब्राउज़र IndexedDB सपोर्ट नहीं करता।",
        true
      );
      return;
    }

    try {
      db = await openDatabase();

      $("vaultCreateBtn").addEventListener("click", createVault);
      $("vaultUnlockBtn").addEventListener("click", unlockVault);
      $("vaultLockBtn").addEventListener("click", lockVault);

      // फोटो/वीडियो चुनने का बटन सेट करें।
      setupFilePicker();

      ["vaultNewPin", "vaultConfirmPin", "vaultPin"].forEach(id => {
        const input = $(id);

        if (!input) return;

        input.addEventListener("input", () => {
          cleanPinInput(input);
        });

        input.addEventListener("keydown", event => {
          if (event.key === "Enter") {
            if (id === "vaultPin") {
              unlockVault();
            } else if (id === "vaultConfirmPin") {
              createVault();
            }
          }
        });
      });

      setupActivityTracking();

      await refreshVaultScreen();

      console.log("Ishwar Private Vault initialized.");

    } catch (error) {
      console.error("Vault initialization error:", error);

      showMessage(
        "Vault शुरू नहीं हो पाया। ब्राउज़र स्टोरेज जाँचें।",
        true
      );
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initVault, {
      once: true
    });
  } else {
    initVault();
  }

})();
