# Yapılandırma Rehberi: Webhook Kurulumu

Ödeme olaylarını (authorization, capture, refund) almak için: (1) Merchant Portal'dan bir webhook uç noktası (endpoint) tanımlayın, (2) paylaşılan gizli anahtarla (secret) gelen isteklerin imzasını doğrulayın, (3) uç noktanızın hızlı bir şekilde HTTP 200 döndürdüğünden emin olun — yavaş yanıtlar birikmeye (backlog) yol açar, bkz. `postmortem_webhook_backlog.md`.
