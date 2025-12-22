;;; init.el ---                                      -*- lexical-binding: t; -*-

;; Copyright (C) 2023  ono

;; Author: ono <ono@localhost.localdomain>

(add-to-list 'load-path "~/.emacs.d/lisps/")
;; ======================================================
;; UI
;; ======================================================
(if (fboundp 'menu-bar-mode) (menu-bar-mode -1))
(if (fboundp 'tool-bar-mode) (tool-bar-mode -1))
(if (fboundp 'scroll-bar-mode) (scroll-bar-mode -1))
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
;; `tab-bar-mode' (built-in since Emacs 27)
;; ======================================================
(setq tab-bar-show nil)
(tab-bar-mode 1)

(global-set-key (kbd "<f11>") 'tab-bar-switch-to-prev-tab)
(global-set-key (kbd "<f12>") 'tab-bar-switch-to-next-tab)

(require 'cl-lib)
(defun my-list-insert-at (lst index elem)
  "Return a new list with ELEM inserted at INDEX."
  (append (cl-subseq lst 0 index)
	  (list elem)
	  (cl-subseq lst index)))

(defun my-mode-line-tab-bar-index ()
  "Get formatted `tab-bar--current-tab-index' for `mode-line-format'."
  (when (and (bound-and-true-p tab-bar-mode)
	     (fboundp 'tab-bar--current-tab-index))
    (format "[%d] " (tab-bar--current-tab-index))))
(defvar my-mode-line-tab-bar-index '(:eval (my-mode-line-tab-bar-index))
  "Used in `mode-line-format' to show the index of `tab-bar-mode'")

;; Setup `mode-line-format' to show tab-bar index in modeline
(let* ((already-inserted (member my-mode-line-tab-bar-index mode-line-format))
       (vc-index (cl-position '(vc-mode vc-mode) mode-line-format :test #'equal)))
  (when (and vc-index (not already-inserted))
    (setq-default mode-line-format
		  (my-list-insert-at mode-line-format
				     vc-index
				     my-mode-line-tab-bar-index))))

;; ======================================================
;; iBuffer
;; ======================================================
(require 'ibuffer)
(global-set-key (kbd "C-x C-b") 'ibuffer)
(autoload 'ibuffer "ibuffer" "List buffers." t)

;; ======================================================
;; Eval & Revert buffer
;; ======================================================
(defun eval-buffer-and-message ()
  (interactive)
  (eval-buffer)
  (message "Eval done!"))
(define-key emacs-lisp-mode-map (kbd "C-c C-e") 'eval-buffer-and-message)

(defun revert-buffer-without-confirm ()
  (interactive)
  (revert-buffer nil t)
  (message "Buffer reverted."))
(global-set-key (kbd "C-c C-r") 'revert-buffer-without-confirm)

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
(global-set-key (kbd "C-x C-S-r") 'recentz-tramp-files)         ;; (Optional, because it's equivalient to C-u C-x C-r)
(global-set-key (kbd "C-x C-S-d") 'recentz-tramp-directories)   ;; (Optional, the reason is same above)
(global-set-key (kbd "C-x C-S-p") 'recentz-tramp-projects)      ;; (Optional, the reason is same above)

;; ======================================================
;; IDO
;; ======================================================

;; Use up/down keys to navigate among Ido candidates
(defun my-ido-bind-key-for-vertical ()
  "Keybindings for vertically-displayed ido-mode candidates list.
(Use up/down to navigate among candidates)"
  (define-key ido-completion-map (kbd "<down>") 'ido-next-match)
  (define-key ido-completion-map (kbd "<up>")   'ido-prev-match))
(add-hook 'ido-setup-hook #'my-ido-bind-key-for-vertical)

;; ======================================================
;; Minibuffer
;; ======================================================
(require 'minibuffer-enhancements)
(savehist-mode t)      ;; Save Minibuffer History

;; ======================================================
;; Minibuffer :: `vertico' - vertical interactive Zsh-liked completion (optional, available in Debian official repo)
;; ======================================================
(when (locate-library "vertico")
  (setq vertico-multiform-commands
	'((describe-symbol (vertico-sort-function . vertico-sort-alpha))))
  (setq vertico-multiform-categories
	'((symbol (vertico-sort-function . vertico-sort-alpha))))
  (vertico-mode t)
  (vertico-grid-mode -1) ;; Show items line-by-line
  (define-key vertico-map "?" #'minibuffer-completion-help)
  (define-key vertico-map (kbd "TAB") #'minibuffer-complete)
  (define-key vertico-map (kbd "M-g") #'vertico-grid-mode)
  ;;(define-key vertico-map (kbd "C-j") #'minibuffer-force-complete-and-exit)
  )

;; ======================================================
;; Minibuffer :: `marginalia' - Show extra info in right-side (optional, available in Debian official repo)
;; ======================================================
(when (locate-library "marginalia")
  (marginalia-mode)      ;; Show elisp description summary in M-x
)
;; ======================================================
;; Minibuffer :: `orderless' - Fuzzy searching for `find-file' & `M-x' (optional, available in Debian official repo)
;; ======================================================
(when (require 'orderless nil 'no-error)
  (setq completion-styles '(orderless))
  (setq completion-category-defaults nil)
  (setq completion-category-overrides '((file (styles partial-completion))))
  )

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

(require 'diredfl)   ; More font-lock for dired.
(diredfl-global-mode)

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
;; Centralized backup / temporary files
;; ======================================================
;; Don't use .#FILENAME
;; https://stackoverflow.com/questions/5738170/why-does-emacs-create-temporary-symbolic-links-for-modified-files/12974060#12974060
;; Non-nil means use lockfiles to avoid editing collisions.
(setq create-lockfiles nil)  ;; Nobody cares multiple editors are editing the same file.

(setq backup-by-copying t)
(setq delete-old-versions t)
(setq kept-new-versions 8)
(setq kept-old-versions 3)
(setq version-control t)

;; https://www.emacswiki.org/emacs/BackupDirectory
;; Local
(defvar my-emacs-tmp-directory       (concat user-emacs-directory "_tmp/") "All directories and files under this folder should be mode of 0o700 and 0o600")
(defvar my-autosavelist-directory    (concat user-emacs-directory "_tmp/autosavelist/") "Auto-save list files (e.g. .saves-*, save-*). See variable `auto-save-list-file-prefix'")
(defvar my-backup-directory          (concat user-emacs-directory "_tmp/backups/") "Centralized backup files (e.g. file~, file.~N~). See variable `backup-directory-alist'")
(defvar my-autosave-directory        (concat user-emacs-directory "_tmp/autosave/") "Centralized auto-save files (e.g. #file#). See variable `auto-save-file-name-transforms'")
(defvar my-undotree-directory        (concat user-emacs-directory "_tmp/undotree/") "Persistent undo-tree history files (e.g. ~undo-tree~*). See variable `undo-tree-history-directory-alist'")
;; TRAMP
(defvar my-tramp-backup-directory    (concat user-emacs-directory "_tmp/tramp/backups/") "For TRAMP. See variable `tramp-backup-directory-alist'")
(defvar my-tramp-autosave-directory  (concat user-emacs-directory "_tmp/tramp/autosave/") "For TRAMP. See variable `tramp-auto-save-directory'")
(defvar my-tramp-persistency-file    (concat user-emacs-directory "_tmp/tramp/tramp_persistency") "For TRAMP. See variable `tramp-persistency-file-name'")
;; Other State
(defvar my-desktop-directory         (concat user-emacs-directory "_tmp/state/desktop/") "For `desktop-save-mode'. See variable `desktop-dirname'")
(defvar my-save-place-file           (concat user-emacs-directory "_tmp/state/save-place") "For `save-place-mode'. See variable `save-place-file'")

;; Ensure the directories are created
(dolist (dir (list my-emacs-tmp-directory
		   my-autosavelist-directory
		   my-backup-directory
		   my-autosave-directory
		   my-undotree-directory
		   my-tramp-backup-directory
		   my-tramp-autosave-directory
		   my-desktop-directory
		   ))
  (make-directory dir t)
  (set-file-modes dir #o700))

(setq auto-save-list-file-prefix (concat my-autosavelist-directory "save-"))
(setq backup-directory-alist `((".*" . ,my-backup-directory)))
(setq auto-save-file-name-transforms `((".*" ,my-autosave-directory t)))
(setq undo-tree-history-directory-alist `((".*" . ,my-undotree-directory)))

(setq tramp-backup-directory-alist `((".*" . ,my-tramp-backup-directory)))
(setq tramp-auto-save-directory my-tramp-autosave-directory)
(setq tramp-persistency-file-name my-tramp-persistency-file)
(setq desktop-dirname my-desktop-directory)
(setq save-place-file my-save-place-file)

(save-place-mode 1)  ; Store cursor places after closing buffer

;; ======================================================
;; apparmor
;; ======================================================
(require 'apparmor-mode)
(add-to-list 'auto-mode-alist '("/etc/apparmor.d/.*" . apparmor-mode))

;; ======================================================
;; YAML
;; ======================================================
(require 'yaml-mode)
(add-to-list 'auto-mode-alist '("\\.ya?ml\\'" . yaml-mode))

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
;; systemd units (`systemd-mode' is available in Debian official repo.)
;; If not found `systemd-mode', use `conf-unix-mode' as fallback.
;; ======================================================
(when (not (locate-library "systemd"))
  (add-to-list 'auto-mode-alist '("\\.service\\'" . conf-unix-mode))
  (add-to-list 'auto-mode-alist '("\\.socket\\'" . conf-unix-mode))
  (add-to-list 'auto-mode-alist '("\\.timer\\'" . conf-unix-mode))
  (add-to-list 'auto-mode-alist '("\\.target\\'" . conf-unix-mode))
  (add-to-list 'auto-mode-alist '("\\.mount\\'" . conf-unix-mode))
  (add-to-list 'auto-mode-alist '("\\.path\\'" . conf-unix-mode)))

;; ======================================================
;; `rainbow-delimiters' (optional, avail in Debian official repo)
;; ======================================================
(when (locate-library "rainbow-delimiters")
  (add-hook 'prog-mode-hook #'rainbow-delimiters-mode))

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

;;======================================================
;; `symbol-overlay' (highlight / jump between symbols)
;;======================================================
(require 'symbol-overlay)
(setq symbol-overlay-idle-time 0.2)
(global-set-key (kbd "C-c M-n") 'symbol-overlay-put)
(global-set-key (kbd "C-M-\"") 'symbol-overlay-put)
(global-set-key (kbd "C-c C-M-\"") 'symbol-overlay-remove-all)
(global-set-key (kbd "M-n") 'symbol-overlay-jump-next)
(global-set-key (kbd "M-p") 'symbol-overlay-jump-prev)
(global-set-key (kbd "C-c M-p") 'symbol-overlay-rename)
(add-hook 'prog-mode-hook 'symbol-overlay-mode)

;; ======================================================
;; `diff-hl' (available in Debian repo, pkg name is `elpa-diff-hl')
;; ======================================================
(when (require 'diff-hl nil 'noerror)
  (global-diff-hl-mode 1)   ; Indicate modified lines according to VC
  (diff-hl-margin-mode 1)   ; Also show character (+-) instead of only color.
  (diff-hl-flydiff-mode 1)  ; Real-time update state
  (add-hook 'dired-mode-hook 'diff-hl-dired-mode-unless-remote) ; In Dired buffer
  (add-hook 'vc-dir-mode-hook #'diff-hl-dir-mode)  ; In `vc-dir' buffer
  )

;; ======================================================
;; `magit' (available in Debian repo, pkg name is `elpa-magit')
;; ======================================================
(global-set-key (kbd "C-x g s") 'magit-status)
(global-set-key (kbd "C-x g l") 'magit-log)
(global-set-key (kbd "C-x g b") 'magit-blame)
(add-to-list 'auto-mode-alist '(".gitmodules" . conf-mode))

(with-eval-after-load 'magit
  (require 'magit)
  (setq git-commit-summary-max-length 600)
  (remove-hook 'git-commit-setup-hook 'git-commit-turn-on-auto-fill)
  (setq magit-log-margin '(t "%Y-%02m-%d %a %H:%M:%S" magit-log-margin-width t 18))
  )

;; ======================================================
;; Markdown
;; ======================================================
(setq markdown-enable-math t)
(setq markdown-fontify-code-blocks-natively t)
(setq markdown-enable-highlighting-syntax t)
(setq markdown-fontify-whole-heading-line t)

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
