# Spostare la raccolta su una VM

Istruzioni per far raccogliere i feed GTFS Real-Time a una VM Ubuntu 24.04
(aarch64) invece che al PC di lavoro.

**Perche'.** Sul PC la copertura reale misurata e' stata del **7,2%**: la
macchina si spegne e va in sospensione, e in ventidue ore di calendario sono
state raccolte novantacinque interrogazioni su millecentoventidue attese. Una VM
sempre accesa risolve il problema alla radice.

**Divisione dei ruoli.** La VM esegue **soltanto** la raccolta. Esperimenti,
test e scrittura del documento restano sul PC, dove il progetto gira per intero.
Sulla VM non vengono installati `clingo`, `scikit-learn`, `matplotlib`, `scipy`
ne' `pytest`.

Ogni blocco di comandi qui sotto e' etichettato con **dove** va eseguito.
Sostituite `<IP_DELLA_VM>` e `<PERCORSO_CHIAVE>` con i vostri valori: non
compaiono da nessuna parte nel repository, che verra' consegnato al docente.

---

## 1. Configurare l'accesso ssh — sul PC (Git Bash)

Invece di ripetere indirizzo e chiave a ogni comando, si definisce una volta un
alias. Da quel momento basta scrivere `ssh vm-icon`.

Prima mettete la chiave in un posto stabile e con i permessi giusti. La chiave
**non va copiata dentro il repository**:

```bash
mkdir -p ~/.ssh
cp "<PERCORSO_CHIAVE>" ~/.ssh/vm-icon.key
chmod 600 ~/.ssh/vm-icon.key
```

Poi aggiungete questo blocco in fondo a `~/.ssh/config`, creandolo se non
esiste. Cambiate solo la riga `HostName`:

```
Host vm-icon
    HostName <IP_DELLA_VM>
    User ubuntu
    IdentityFile ~/.ssh/vm-icon.key
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 4
```

Un modo rapido per aggiungerlo senza aprire un editor:

```bash
cat >> ~/.ssh/config <<'FINE'

Host vm-icon
    HostName <IP_DELLA_VM>
    User ubuntu
    IdentityFile ~/.ssh/vm-icon.key
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 4
FINE
```

Ricordate di sostituire `<IP_DELLA_VM>` **dopo** averlo incollato.

Verifica:

```bash
ssh vm-icon 'echo "connessione riuscita su $(hostname), $(uname -m)"'
```

Deve rispondere qualcosa come `connessione riuscita su icon-vm, aarch64`. Se
chiede una password, la chiave non e' quella giusta; se resta appeso, controllate
che la porta 22 sia aperta nelle regole di rete di Oracle.

`ServerAliveInterval` serve a non far cadere le sessioni lunghe, per esempio
mentre si trasferiscono i dati.

---

## 2. Fuso orario della VM — sulla VM

```bash
ssh vm-icon
timedatectl | grep -i "time zone"
```

Se non e' `Europe/Rome`:

```bash
sudo timedatectl set-timezone Europe/Rome
```

**Una precisazione, perche' l'intuizione qui inganna.** Le cartelle giornaliere
dei dump **non** dipendono dal fuso della macchina: il collector legge
`fuso_orario: Europe/Rome` da `config.yaml` e calcola la data di servizio con
quello, quindi una VM lasciata in UTC produrrebbe comunque le cartelle giuste.
E' stato verificato forzando tre fusi di sistema diversi e ottenendo la stessa
cartella.

Impostare `Europe/Rome` resta comunque la cosa giusta da fare, per due motivi
concreti: gli orari nel log e in `journalctl` diventano leggibili senza
conversioni mentali, e il timer del consolidamento notturno, che arrivera' in un
secondo momento, deve scattare alle quattro del mattino italiane e non alle sei.

---

## 3. Clonare il repository — sulla VM

```bash
sudo apt update
sudo apt install -y git python3-venv
git clone <URL_DEL_REPOSITORY> ~/icon
cd ~/icon
```

Se il repository non e' su un server remoto, si puo' copiarlo dal PC:

```bash
# sul PC (Git Bash), dalla cartella del progetto
tar czf - --exclude=.venv --exclude=data --exclude=logs . | ssh vm-icon 'mkdir -p ~/icon && tar xzf - -C ~/icon'
```

`config.yaml` fa parte del repository, quindi gli indirizzi dei feed sono gia'
configurati e non c'e' nulla da compilare.

---

## 4. Installare — sulla VM

```bash
cd ~/icon
./deploy/install.sh
```

Lo script crea l'ambiente virtuale, installa le sei dipendenze verificate per
aarch64, controlla che protobuf, PyYAML e i fusi orari funzionino davvero su
questa architettura, valida `config.yaml`, genera la unit systemd con i percorsi
reali e la abilita all'avvio della macchina.

**Non avvia il servizio**, e lo dice esplicitamente alla fine. Non e' un errore:
i dati gia' raccolti vanno copiati prima (passo 5). E' idempotente, quindi
rieseguirlo in futuro aggiorna l'installazione senza rompere nulla.

Se qualcosa manca, lo script si ferma dicendo quale comando risolve il problema.

---

## 5. Copiare i dati gia' raccolti — sul PC (Git Bash)

**Questo passo va fatto prima di avviare il servizio.** Sul PC ci sono i dump
del 25 e 26 agosto, gli archivi statici GTFS, i manifest, `index.json` e
`gaps.jsonl`. Copiarli mantiene coerente la storia della raccolta.

```bash
cd /c/Users/MSI/Desktop/ICON
tar czf - data/raw | ssh vm-icon 'tar xzf - -C ~/icon'
```

Sono circa 250 MB non compressi; il trasferimento richiede qualche minuto. Non
serve `rsync`, che Git Bash non include: `tar` e `ssh` bastano e ci sono gia'.

Verifica, sulla VM:

```bash
ssh vm-icon 'find ~/icon/data/raw/rt -name "*.pb" | wc -l; ls ~/icon/data/raw/gtfs/*/'
```

Il conteggio deve corrispondere a quello del PC, e devono comparire i quattro
archivi `.zip` piu' i due `index.json`.

**Cosa succede al primo avvio, ed e' giusto che succeda.** Il collector trovera'
`_battito.json` con l'ultima raccolta riuscita sul PC, e registrera' in
`gaps.jsonl` una interruzione che va da quel momento all'avvio sulla VM. Non e'
un difetto: quella interruzione e' reale, ed e' esattamente il dato che serve per
escludere quella finestra dal backtesting e per dichiarare la copertura onesta
nella documentazione. Se invece aveste avviato il servizio **prima** della copia,
la VM avrebbe iniziato una storia nuova e quella finestra sarebbe sparita senza
lasciare traccia.

---

## 6. Avviare la raccolta — sulla VM

```bash
sudo systemctl start collector-tpl
```

---

## 7. Verificare in due minuti che stia raccogliendo davvero — sulla VM

**Primo controllo: il servizio e' vivo.**

```bash
systemctl status collector-tpl --no-pager
```

Deve dire `active (running)`. Se dice `failed`, il motivo e' nelle ultime righe.

**Secondo controllo: guardate due giri passare.**

```bash
journalctl -u collector-tpl -f
```

Entro un paio di minuti devono comparire le righe di avvio e i salvataggi.
Uscite con `Ctrl+C`. Se compare la riga sull'interruzione registrata, e' quella
attesa del passo 5.

**Terzo controllo, il piu' importante: contano i file, non i log.**

```bash
find ~/icon/data/raw/rt -name '*.pb' -newermt '-3 minutes' | wc -l
```

Dopo tre minuti di esecuzione il numero deve essere attorno a **12**: due citta'
per due feed per tre giri. Se e' zero, la raccolta non sta scrivendo, e il
motivo sara' nel `journalctl`.

**Quarto controllo: l'esito delle interrogazioni.**

```bash
tail -n 5 ~/icon/data/raw/rt/roma/$(date +%F)/_manifest.csv
```

La colonna `esito` deve dire `salvato` o `duplicato`. Qualunque altra cosa e' un
problema da guardare.

Dopo un'ora, il conteggio complessivo dei dump del giorno deve essere vicino a
240, cioe' sessanta giri per quattro feed.

---

## 8. Comandi utili

Sulla VM:

```bash
sudo systemctl stop collector-tpl        # fermare (uscita ordinata, senza file a meta')
sudo systemctl restart collector-tpl     # riavviare
journalctl -u collector-tpl -n 50        # ultime 50 righe
journalctl -u collector-tpl --since today | grep -i "ultima ora"   # riepiloghi orari
df -h ~/icon                             # spazio libero
```

Dal PC:

```bash
ssh vm-icon 'systemctl is-active collector-tpl'
ssh vm-icon 'find ~/icon/data/raw/rt -name "*.pb" | wc -l'
```

---

## 9. Rimuovere il compito pianificato di Windows

**Solo dopo aver verificato che la VM raccoglie** (passo 7), sul PC, in
PowerShell:

```powershell
schtasks /end    /tn "RaccoltaTPL"
schtasks /delete /tn "RaccoltaTPL" /f
```

Lasciarli attivi entrambi non corrompe i dati, perche' scrivono su macchine
diverse, ma produrrebbe due storie parallele da riconciliare a mano.

---

## 10. Un'avvertenza sulla VM

Se l'istanza e' di tipo "Always Free", verificate sulla documentazione di Oracle
la politica di recupero delle istanze inattive: una raccolta che interroga due
feed al minuto usa pochissime risorse. Non conosciamo le soglie applicabili al
vostro contratto e non le riportiamo qui per non affermare cifre non verificate.
