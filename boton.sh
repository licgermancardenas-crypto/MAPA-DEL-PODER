#!/usr/bin/env bash
# Lo que ejecuta el acceso directo del escritorio: corre la actualización y espera una tecla.
cd "$(dirname "$0")"
./actualizar.sh
echo
read -rp "Listo. Enter para cerrar esta ventana. "
