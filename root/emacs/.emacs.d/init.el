;;; init.el ---                                      -*- lexical-binding: t; -*-

;; Copyright (C) 2023  ono

;; Author: ono <ono@localhost.localdomain>

(add-to-list 'load-path "~/.emacs.d/lisps/")
;; ======================================================
;; UI
;; ======================================================
(if (fboundp 'menu-bar-mode) (menu-bar-mode -1))
(if (fboundp 'tool-bar-mode) (tool-bar-mode -1))
;; (if (fboundp 'scroll-bar-mode) (scroll-bar-mode -1))
(setq inhibit-splash-screen t)

;; ======================================================
;; Theme
;; ======================================================
(add-to-list 'custom-theme-load-path "~/.emacs.d/lisps/")
(load-theme 'moe-dark :no-confirm)
(set-face-attribute 'mode-line nil :background "#ef2929" :foreground "#ffffff")
(set-face-attribute 'mode-line-buffer-id nil :background "#ef2929" :foreground "#080808")
(set-face-attribute 'minibuffer-prompt nil :foreground "#a40000" :background "#ffafaf")

;; ======================================================
;; iBuffer
;; ======================================================
(require 'ibuffer)
(global-set-key (kbd "C-x C-b") 'ibuffer)
(autoload 'ibuffer "ibuffer" "List buffers." t)

;; ======================================================
;; Recent files
;; ======================================================
(require 'recentz)  ; fuck recentf
(setq ido-separator "\n")
(setq max-mini-window-height 0.5)   ; higher minibuffer
;; If you prefer (Emacs built-in) IDO
(global-set-key (kbd "C-x C-r") 'recentz-files)
(global-set-key (kbd "C-x C-d") 'recentz-directories)
(global-set-key (kbd "C-x C-p") 'recentz-projects)

;; ======================================================
;; Other mine
;; ======================================================
(require 'minibuffer-enhancements)

;; ======================================================
;; Dired
;; ======================================================
(require 'dired)
(defun my-dired-backward ()
  "Go back to the parent directory (..), and the cursor will be moved to where
the previous directory."
  (interactive)
  (let* ((DIR (or (uniquify-buffer-base-name)
                  (buffer-name))))
    (if (equal DIR "*Find*")
        (quit-window t)
      (progn (find-alternate-file "..")
             (goto-char (point-min))
             (while (and (not (eobp))
                         (not (equal (dired-get-filename t :no-error) DIR)))
               (next-line))
             ;;(revert-buffer)
             ))))

;; Always use the current Dired buffer to open the next directory
(defun dired-my-find-alternate-file ()
  (interactive)
  (if (file-regular-p (dired-get-filename))
      (dired-find-file)
    (dired-find-alternate-file)))

(define-key dired-mode-map (kbd "RET") 'dired-my-find-alternate-file) ; enter to open
(put 'dired-find-alternate-file 'disabled nil) ; avoid dired from asking some annoying question
(define-key dired-mode-map (kbd "q") 'my-dired-backward)  ; q to go upward


;; ======================================================
;; Shell
;; ======================================================
(require 'subr-x)
(cond ((member system-type '(darwin gnu/linux))
       (setq shell-file-name "/bin/zsh")
       (setq shell-command-switch "-c")
       (if (boundp 'exec-path-from-shell-initialize) (exec-path-from-shell-initialize)))
      ((member system-type 'cygwin) (setq shell-file-name "/bin/bash")))

;; ======================================================
;; Backup files
;; ======================================================
;; https://www.emacswiki.org/emacs/BackupDirectory
(defvar --backup-directory (concat user-emacs-directory "_tmp/backups"))
(defvar --undotree-directory (concat user-emacs-directory "_tmp/undotree"))

(setq backup-directory-alist
      `((".*" . ,temporary-file-directory)))
(setq auto-save-file-name-transforms
      `((".*" ,temporary-file-directory t)))
(setq undo-tree-history-directory-alist
      `((".*" . ,temporary-file-directory)))

;; ======================================================
;; apparmor
;; ======================================================
(require 'apparmor-mode)
(add-to-list 'auto-mode-alist '("/etc/apparmor.d/.*" . apparmor-mode))

;; ======================================================
;; Misc
;; ======================================================
(global-auto-revert-mode t)
(global-display-line-numbers-mode 1)

;; Don't ignore .git/ when find-file
(setq completion-ignored-extensions (remove ".git/" completion-ignored-extensions))

;; C-x C-f ignore-case
(setq read-file-name-completion-ignore-case t)
(setq require-final-newline t)
;; highlight current line
(global-hl-line-mode 1)
(show-paren-mode t)


;; ======================================================
;; Make window status undo-able
;; ======================================================
(require 'winner)
(winner-mode 1)

;; ======================================================
;; Window navigation
;; ======================================================
(global-set-key (kbd "M-S") 'windmove-up)
(global-set-key (kbd "M-X") 'windmove-down)
(global-set-key (kbd "M-C") 'windmove-right)
(global-set-key (kbd "M-Z") 'windmove-left)

;; ======================================================
;; hippie expand
;; ======================================================
(global-set-key [(meta ?/)] 'hippie-expand)
(setq hippie-expand-try-functions-list
      '(try-expand-dabbrev
        try-expand-dabbrev-visible
        try-expand-dabbrev-all-buffers
        try-expand-dabbrev-from-kill
        try-complete-file-name-partially
        try-complete-file-name
        try-expand-all-abbrevs
        try-expand-list
        try-expand-line
        try-complete-lisp-symbol-partially
        try-complete-lisp-symbol))

;; ======================================================
;; Undo-tree and redo
;; ======================================================
(require 'undo-tree)
(global-undo-tree-mode)
(global-set-key (kbd "C-M-_") 'undo-tree-redo)
(global-set-key (kbd "M-?") 'undo-tree-redo)

;; ======================================================
;; Undo-tree and redo
;; ======================================================
(require 'undo-tree)
(global-undo-tree-mode)
(global-set-key (kbd "C-M-_") 'undo-tree-redo)
(global-set-key (kbd "M-?") 'undo-tree-redo)

;; ======================================================
;; systemd units
;; ======================================================
(add-to-list 'auto-mode-alist '("\\.service\\'" . conf-unix-mode))
(add-to-list 'auto-mode-alist '("\\.socket\\'" . conf-unix-mode))
(add-to-list 'auto-mode-alist '("\\.timer\\'" . conf-unix-mode))
(add-to-list 'auto-mode-alist '("\\.target\\'" . conf-unix-mode))
(add-to-list 'auto-mode-alist '("\\.mount\\'" . conf-unix-mode))
(add-to-list 'auto-mode-alist '("\\.path\\'" . conf-unix-mode))

;;======================================================
;; multiple-cursors / move-text / duplicate-thing
;;======================================================
(add-to-list 'load-path "~/.emacs.d/lisps/multiple-cursors")
(require 'multiple-cursors)
(require 'move-text)
(require 'duplicate-thing)
(move-text-default-bindings)

(if (window-system)
    (progn
      ;; Follow my VSCode configuration in GUI Emacs
      (global-set-key (kbd "M-S-<up>") 'mc/mark-previous-like-this)
      (global-set-key (kbd "M-S-<down>") 'mc/mark-next-like-this)
      (global-set-key (kbd "C-c M-'") 'mc/mark-all-like-this)
      (global-set-key [M-down] 'move-text-down)
      (global-set-key [M-up]   'move-text-up)
      (global-set-key (kbd "M-'") 'mc/mark-next-like-this-symbol)
      (global-set-key (kbd "M-\"") 'mc/mark-previous-like-this-symbol)
      (global-set-key (kbd "C-S-d") 'duplicate-thing)
      (global-set-key (kbd "C-z") 'undo-tree-undo)
      (global-set-key (kbd "C-S-z") 'undo-tree-redo)
      )
  (progn
    (global-set-key [M-down] 'move-text-down)
    (global-set-key [M-up]   'move-text-up)
    (global-set-key (kbd "C-c d l") 'duplicate-thing)
    (global-set-key (kbd "M-'") 'mc/mark-next-like-this-symbol)
    (global-set-key (kbd "M-\"") 'mc/mark-previous-like-this-symbol)
    (global-set-key (kbd "C-c M-'") 'mc/mark-all-like-this)
    ))

(define-key mc/mark-more-like-this-extended-keymap (kbd "DEL") 'backward-delete-char-untabify)

;; ============================================
;; Coldnew's Font Size Conf for Org-Table
;; ============================================
(defun get-screen-pixel-density ()
  "Return nil on terminal.
Otherwise, return DPI (1 inch = 2.54 cm)
"
  (let* ((screen0 (car (display-monitor-attributes-list)))
         (mm (alist-get 'mm-size screen0))
         (px (alist-get 'geometry screen0))
         (w-mm (nth 0 mm))
         (w-px (nth 2 px))
         )
    (if (eq w-mm nil)
        nil
      (* 25.4 (/ w-px (float w-mm)))
      )))

(defun my-setup-font ()
  (interactive)
  (when (window-system)
    (if (eq system-type 'windows-nt)
	(set-face-attribute 'default nil :font "Consolas-9"))
    (if (eq system-type 'windows-nt)
	(setq emacs-cjk-font "Consolas"
              emacs-english-font "Consolas"))

    (defvar emacs-english-font "DejaVu Sans Mono" "The font name of English.")
    (defvar emacs-cjk-font "Noto Sans CJK JP" "The font name for CJK.")
  ;;; for test
    ;; (find-font (font-spec :name "LiHei Pro"))
    ;; (font-family-list)

    (defvar emacs-font-size-pair '(12 . 14)
      "Default font size pair for (english . chinese)")

    ;; Auto adjust font-size for Hi-res screen
    (let ((dpi (get-screen-pixel-density)))
      (setq emacs-font-size-pair
            (cond
             ((eq dpi nil) (error "This should not be executed under terminal."))
             ((> dpi 150) '(17 . 20))
             (t '(12 . 14))
             )))

    (defvar emacs-font-size-pair-list
      '(( 5 .  6) (9 . 10) (10 . 12)(12 . 14)
	(13 . 16) (15 . 18) (17 . 20) (19 . 22)
	(20 . 24) (21 . 26) (24 . 28) (26 . 32)
	(28 . 34) (30 . 36) (34 . 40) (36 . 44))
      "This list is used to store matching (englis . chinese) font-size.")

    (defun font-exist-p (fontname)
      "Test if this font is exist or not."
      (if (or (not fontname) (string= fontname ""))
          nil
	(if (not (x-list-fonts fontname)) nil t)))

    (defun set-font (english chinese size-pair)
      "Setup emacs English and Chinese font on x window-system."

      (if (font-exist-p english)
          (set-frame-font (format "%s:pixelsize=%d" english (car size-pair)) t))

      (if (font-exist-p chinese)
          (dolist (charset '(kana han symbol cjk-misc bopomofo))
            (set-fontset-font (frame-parameter nil 'font) charset
                              (font-spec :family chinese :size (cdr size-pair))))))
    ;; Setup font size based on emacs-font-size-pair
    (set-font emacs-english-font emacs-cjk-font emacs-font-size-pair)

    (defun emacs-step-font-size (step)
      "Increase/Decrease emacs's font size."
      (let ((scale-steps emacs-font-size-pair-list))
	(if (< step 0) (setq scale-steps (reverse scale-steps)))
	(setq emacs-font-size-pair
              (or (cadr (member emacs-font-size-pair scale-steps))
                  emacs-font-size-pair))
	(when emacs-font-size-pair
          (message "emacs font size set to %.1f" (car emacs-font-size-pair))
          (set-font emacs-english-font emacs-cjk-font emacs-font-size-pair))))

    (defun increase-emacs-font-size ()
      "Decrease emacs's font-size acording emacs-font-size-pair-list."
      (interactive) (emacs-step-font-size 1))

    (defun decrease-emacs-font-size ()
      "Increase emacs's font-size acording emacs-font-size-pair-list."
      (interactive) (emacs-step-font-size -1))

    (global-set-key (kbd "C-=") 'increase-emacs-font-size)
    (global-set-key (kbd "C--") 'decrease-emacs-font-size)
    )
  )
(my-setup-font)

(add-hook 'server-after-make-frame-hook 'my-setup-font)  ; setup for emacs daemon & client
