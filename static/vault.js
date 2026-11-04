
/* =====================================================
   ISHWAR PRIVATE VAULT
   Local-only encrypted photo and video storage
   Encryption: AES-GCM 256-bit
   Key derivation: PBKDF2 / SHA-256
===================================================== */

(() => {
  "use strict";

  const DB_NAME = "ishwar_private_vault_v1";
  const DB_VERSION = 1;
  const META_STORE = "meta";
  const FILE_STORE = "files";

  const PBKDF2_ITERATIONS = 310000;
  const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50 MB per file
  const AUTO_LOCK_TIME = 5 * 60 * 1000; // 5 minutes

  const CHECK_TEXT = "ISHWAR_PRIVATE_VAULT_OK";

  let db = null;
  let vaultKey = null;
  let autoLockTimer = null;
  let objectUrls = [];
  let unlockedFiles = new Map();

  const $ = (id) => document.getElementById(id);

  /* -----------------------------
     MESSAGE / STATUS
  ----------------------------- */

  function showMessage(message, isError = false) {
    let messageBox = $("vaultMessage");

    if (!messageBox) {
      messageBox = document.createElement("p");
      messageBox.id = "vaultMessage";
      messageBox.setAttribute("aria-live", "polite");
      messageBox.style.margin = "12px 0";
      messageBox.style.padding = "10px";
      messageBox.style.borderRadius = "8px";

      const panel = $("vaultPanel");

      if (panel) {
        const intro = panel.querySelector("p");

        if (intro) {
          intro.insertAdjacentElement("afterend", messageBox);
        } else {
          panel.prepend(messageBox);
        }
      }
    }

    messageBox.textContent = message;
    messageBox.style.color = isError ? "#ff8585" : "#70e6b2";
    messageBox.style.background = isError
      ? "#401c25"
      : "#12352b";
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
     BASIC HELPERS
  ----------------------------- */

  function randomBytes(length) {
    const bytes = new Uint8Array(length);
    crypto.getRandomValues(bytes);
    return bytes;
  }

  function bytesToHex(bytes) {
    return Array.from(bytes)
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
  }

  function makeId() {
    if (crypto.randomUUID) {
      return crypto.randomUUID();
    }

    return bytesToHex(randomBytes(16));
  }

  function isValidPin(pin) {
    return /^\d{6}$/.test(pin);
  }

  function cleanPinInput(input) {
    if (!input) return;

    input.value = input.value
      .replace(/\D/g, "")
      .slice(0, 6);
  }

  function bufferToBytes(buffer) {
    return new Uint8Array(buffer);
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

      request.onsuccess = () => {
        resolve(request.result);
      };

      request.onerror = () => {
        reject(request.error);
      };

      request.onblocked = () => {
        reject(new Error("Database is busy. Please reload the page."));
      };
    });
  }

  function getRecord(storeName, id) {
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(storeName, "readonly");
      const store = transaction.objectStore(storeName);
      const request = store.get(id);

      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
  }

  function getAllRecords(storeName) {
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(storeName, "readonly");
      const store = transaction.objectStore(storeName);
      const request = store.getAll();

      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => reject(request.error);
    });
  }

  function saveRecord(storeName, record) {
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(storeName, "readwrite");
      const store = transaction.objectStore(storeName);

      store.put(record);

      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  }

  function deleteRecord(storeName, id) {
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(storeName, "readwrite");
      const store = transaction.objectStore(storeName);

      store.delete(id);

      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  }

  /* -----------------------------
     ENCRYPTION KEY
  ----------------------------- */

  async function deriveKey(pin, salt) {
    const encoder = new TextEncoder();

    const pinKey = await crypto.subtle.importKey(
      "raw",
      encoder.encode(pin),
      "PBKDF2",
      false,
      ["deriveKey"]
    );

    return crypto.subtle.deriveKey(
      {
        name: "PBKDF2",
        salt: salt,
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
        iv: iv
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
        iv: bufferToBytes(iv)
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
      const existingMeta = await getRecord(META_STORE, "vault");

      if (existingMeta) {
        showMessage("Vault पहले से बना हुआ है। उसे Unlock करें।", true);
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
        checkData: checkData
      });

      vaultKey = key;

      $("vaultNewPin").value = "";
      $("vaultConfirmPin").value = "";

      showMessage("आपका Private Vault बन गया है।");
      await showUnlockedVault();

    } catch (error) {
      console.error("Vault creation error:", error);
      showMessage(
        "Vault नहीं बन पाया। ब्राउज़र स्टोरेज और HTTPS कनेक्शन जाँचें।",
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
        showMessage("Vault नहीं मिला। पहले नया Vault बनाएँ।", true);
        await refreshVaultScreen();
        return;
      }

      const key = await deriveKey(
        pin,
        bufferToBytes(meta.salt)
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
      console.error("Vault unlock failed:", error);
      showMessage("गलत PIN या Vault डेटा पढ़ने में समस्या।", true);
    } finally {
      if (button) button.disabled = false;
    }
  }

  /* -----------------------------
     PACK FILE + PRIVATE METADATA
     Metadata is encrypted along
     with the actual file bytes.
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

    const fileBytes = new Uint8Array(await file.arrayBuffer());

    const packed = new Uint8Array(
      4 + metadataBytes.length + fileBytes.length
    );

    const view = new DataView(packed.buffer);
    view.setUint32(0, metadataBytes.length);

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
      throw new Error("Invalid encrypted file");
    }

    const view = new DataView(bytes.buffer);
    const metadataLength = view.getUint32(0);

    if (metadataLength > bytes.length - 4) {
      throw new Error("Invalid file metadata");
    }

    const metadataBytes = bytes.slice(4, 4 + metadataLength);
    const fileBytes = bytes.slice(4 + metadataLength);

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
     ADD PHOTO / VIDEO
  ----------------------------- */

  async function addFiles(fileList) {
    if (!vaultKey) {
      showMessage("पहले Vault Unlock करें।", true);
      return;
    }

    const files = Array.from(fileList || []);

    if (!files.length) return;

    const input = $("vaultFiles");
    if (input) input.value = "";

    for (const file of files) {
      if (
        !file.type.startsWith("image/") &&
        !file.type.startsWith("video/")
      ) {
        setVaultStatus(
          `${file.name}: केवल फोटो और वीडियो जोड़े जा सकते हैं।`,
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
        console.error("File encryption error:", error);

        if (
          error?.name === "QuotaExceededError" ||
          error?.name === "NS_ERROR_DOM_QUOTA_REACHED"
        ) {
          setVaultStatus(
            "डिवाइस की ब्राउज़र स्टोरेज भर गई है। कुछ जगह खाली करें।",
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
     GALLERY CLEANUP
  ----------------------------- */

  function clearGallery() {
    objectUrls.forEach((url) => {
      URL.revokeObjectURL(url);
    });

    objectUrls = [];
    unlockedFiles.clear();

    const gallery = $("vaultGallery");

    if (gallery) {
      gallery.replaceChildren();
    }
  }

  /* -----------------------------
     LOAD GALLERY
  ----------------------------- */

  async function loadGallery() {
    if (!vaultKey) return;

    const gallery = $("vaultGallery");
    if (!gallery) return;

    clearGallery();

    const records = await getAllRecords(FILE_STORE);

    if (!records.length) {
      const empty = document.createElement("div");
      empty.className = "vault-empty";
      empty.textContent = "अभी Vault में कोई फोटो या वीडियो नहीं है।";

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

        unlockedFiles.set(record.id, {
          url,
          metadata: result.metadata
        });

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
          const confirmed = window.confirm(
            "क्या आप इस फाइल को Vault से हमेशा के लिए डिलीट करना चाहते हैं?"
          );

          if (!confirmed) return;

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
        console.error("Could not decrypt a vault file:", error);

        const errorItem = document.createElement("div");
        errorItem.className = "vault-empty";
        errorItem.textContent =
          "एक फाइल पढ़ी नहीं जा सकी। उसका डेटा खराब हो सकता है।";

        gallery.appendChild(errorItem);
      }
    }
  }

  function formatFileSize(bytes) {
    const size = Number(bytes) || 0;

    if (size < 1024) return `${size} Bytes`;
    if (size < 1024 * 1024) {
      return `${(size / 1024).toFixed(1)} KB`;
    }

    return `${(size / (1024 * 1024)).toFixed(2)} MB`;
  }

  /* -----------------------------
     SHOW UNLOCKED VAULT
  ----------------------------- */

  async function showUnlockedVault() {
    if ($("vaultSetup")) $("vaultSetup").hidden = true;
    if ($("vaultUnlock")) $("vaultUnlock").hidden = true;
    if ($("vaultContent")) $("vaultContent").hidden = false;

    await loadGallery();
    resetAutoLockTimer();
  }

  /* -----------------------------
     LOCK VAULT
  ----------------------------- */

  function lockVault() {
    clearTimeout(autoLockTimer);
    autoLockTimer = null;

    clearGallery();

    // Drop the JavaScript reference to the key.
    vaultKey = null;

    if ($("vaultContent")) $("vaultContent").hidden = true;

    refreshVaultScreen();

    showMessage("Vault Lock कर दिया गया है।");
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
    const events = [
      "click",
      "keydown",
      "touchstart",
      "mousemove"
    ];

    events.forEach((eventName) => {
      document.addEventListener(
        eventName,
        () => {
          if (vaultKey) resetAutoLockTimer();
        },
        { passive: true }
      );
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
     REFRESH VAULT SCREEN
  ----------------------------- */

  async function refreshVaultScreen() {
    try {
      const meta = await getRecord(META_STORE, "vault");

      if (meta) {
        if ($("vaultSetup")) $("vaultSetup").hidden = true;
        if ($("vaultUnlock")) $("vaultUnlock").hidden = false;
      } else {
        if ($("vaultSetup")) $("vaultSetup").hidden = false;
        if ($("vaultUnlock")) $("vaultUnlock").hidden = true;
      }

      if ($("vaultContent")) $("vaultContent").hidden = true;

    } catch (error) {
      console.error(error);
      showMessage("Vault की जानकारी पढ़ने में समस्या हुई।", true);
    }
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

    const missing = requiredElements.filter((id) => !$(id));

    if (missing.length) {
      console.error("Vault HTML elements missing:", missing);
      return;
    }

    if (!window.isSecureContext || !crypto?.subtle) {
      showMessage(
        "Vault के लिए सुरक्षित HTTPS कनेक्शन और Web Crypto सपोर्ट जरूरी है।",
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
$("vaultChooseFilesBtn").addEventListener("click", () => {
  $("vaultFiles").click();
});
       const chooseFilesButton = $("vaultChooseFilesBtn");

if (chooseFilesButton) {
  chooseFilesButton.addEventListener("click", () => {
    $("vaultFiles").click();
  });
}
      $("vaultFiles").addEventListener("change", (event) => {
        addFiles(event.target.files);
      });

      ["vaultNewPin", "vaultConfirmPin", "vaultPin"].forEach((id) => {
        const input = $(id);

        if (input) {
          input.addEventListener("input", () => {
            cleanPinInput(input);
          });

          input.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
              if (id === "vaultPin") {
                unlockVault();
              } else if (id === "vaultConfirmPin") {
                createVault();
              }
            }
          });
        }
      });

      setupActivityTracking();
      await refreshVaultScreen();

      console.log("Ishwar Private Vault initialized.");

    } catch (error) {
      console.error("Vault initialization error:", error);
      showMessage(
        "Vault शुरू नहीं हो पाया। ब्राउज़र स्टोरेज की अनुमति जाँचें।",
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
