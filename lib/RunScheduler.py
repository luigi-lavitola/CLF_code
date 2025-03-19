import datetime

class RunScheduler:
    def __init__(self, file_path):
        """Inizializza la classe caricando il file calendario."""
        self.file_path = file_path
    
    def calcola_orario_con_data(self, data, orario, offset_minuti):
        """Calcola un nuovo orario con un certo offset di minuti, gestendo il passaggio di data."""
        anno, mese, giorno = map(int, data.split())
        h, m, s = map(int, orario.split())

        timestamp = datetime.datetime(anno, mese, giorno, h, m, s) + datetime.timedelta(minutes=offset_minuti)
        return timestamp.strftime("%Y %m %d"), timestamp.strftime("%H %M %S")

    def genera_orari_clf(self, data_inizio, orario_inizio, data_fine, orario_fine, has_raman_430):
        """Genera orari CLF ai minuti 15, 30, 45 tra inizio e fine turno, evitando il Run Raman delle 04:30."""
        anno_i, mese_i, giorno_i = map(int, data_inizio.split())
        anno_f, mese_f, giorno_f = map(int, data_fine.split())

        h_i, m_i, s_i = map(int, orario_inizio.split())
        h_f, m_f, s_f = map(int, orario_fine.split())

        start_time = datetime.datetime(anno_i, mese_i, giorno_i, h_i, m_i, s_i)
        end_time = datetime.datetime(anno_f, mese_f, giorno_f, h_f, m_f, s_f)

        # Trova il primo orario valido (XX:15, XX:30, XX:45)
        while start_time.minute not in [15, 30, 45]:
            start_time += datetime.timedelta(minutes=1)

        clf_orari = []
        while start_time <= end_time:
            if has_raman_430 and start_time.strftime("%H:%M") == "04:30":
                start_time += datetime.timedelta(minutes=15)
                continue
            clf_orari.append((start_time.strftime("%H %M %S"), "CLF Run"))
            start_time += datetime.timedelta(minutes=15)

        return clf_orari

    def estrai_info_per_data(self, data_cercata):
        """Estrae informazioni dai dati del calendario per una data specifica."""
        info = []
        with open(self.file_path, "r") as file:
            for linea in file:
                elementi = linea.split()
                if len(elementi) >= 11:
                    shift_fd = int(elementi[0])
                    data_inizio = " ".join(elementi[1:4])
                    orario_inizio = " ".join(elementi[4:7])
                    data_fine = " ".join(elementi[7:10])
                    orario_fine = " ".join(elementi[10:13])

                    if data_inizio == data_cercata:
                        has_raman_430 = shift_fd > 0
                        raman_prima = self.calcola_orario_con_data(data_inizio, orario_inizio, -30)
                        raman_dopo = self.calcola_orario_con_data(data_fine, orario_fine, 30)
                        raman_fisso = ("04 30 00", "Raman Run Fisso") if has_raman_430 else None
                        clf_orari = self.genera_orari_clf(data_inizio, orario_inizio, data_fine, orario_fine, has_raman_430) if has_raman_430 else []

                        info.append({
                            "data": data_inizio,
                            "orari": [
                                (raman_prima[1], "Raman Run Prima"),
                                (raman_dopo[1], "Raman Run Dopo"),
                            ] + ([raman_fisso] if raman_fisso else []) + clf_orari
                        })
        return info

    def get_run_info(self, date=None):
        """Restituisce un dizionario con TUTTI gli orari di run per la data specificata."""
        if date is None:
            date = datetime.datetime.today().strftime("%Y %m %d")
        
        runs = self.estrai_info_per_data(date)
        run_dict = {}

        for entry in runs:
            date_key = entry["data"]  # Usa la data come chiave principale
            if date_key not in run_dict:
                run_dict[date_key] = []  # Inizializza la lista degli orari

            for run in entry["orari"]:
                run_dict[date_key].append({"type": run[1], "time": run[0]})

        return run_dict


