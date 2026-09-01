# Plano de melhoramento da base de dados

## Objetivo

No final de cada sincronização de uma playlist, garantir que:

- A playlist fica registada na base de dados.
- Cada track da playlist fica registada ou atualizada na base de dados.
- A relação entre a playlist e cada track fica garantida, mesmo quando a track já existia.
- É possível consultar, para cada playlist, o total de tracks, quantas têm ficheiro FLAC e quantas têm ficheiro MP3.
- É possível obter os nomes das tracks da playlist que não têm qualquer ficheiro local.

Este documento descreve apenas o plano. Não inclui implementação.

## Estado atual

### Estrutura existente

O módulo `spotidal/model/library.py` já define estas tabelas:

- `tracks`: metadados da track, incluindo `spotify_id` e `tidal_id`.
- `files`: ficheiros locais associados a uma track, com `format`, `path` e `missing_at`.
- `playlists`: playlists identificadas por nome, com IDs do Spotify e do TIDAL.
- `playlist_tracks`: relação muitos-para-muitos entre playlists e tracks, protegida por uma chave primária composta.

O watcher e o processo de reconciliação já importam ficheiros `.flac` e `.mp3` para `files`, e marcam ficheiros removidos com `missing_at`.

### Lacuna atual

O fluxo de sync em `spotidal/model/helpers/synchronizer.py` atualiza a playlist no TIDAL, mas não persiste no final o resultado do mapeamento Spotify-TIDAL na `MusicLibrary`.

Também é necessário tratar separadamente estes casos:

- A track já existe em `tracks`, mas ainda não existe em `playlist_tracks`.
- A track foi encontrada no Spotify, mas não foi encontrada no TIDAL.
- A track existe na playlist, mas ainda não tem ficheiro local.
- O ficheiro existia na base de dados, mas está atualmente marcado como ausente.

## Decisões de modelo

### Identidade das entidades

1. Usar o ID da playlist do Spotify como referência externa principal quando disponível.
2. Usar o ID da track do Spotify e/ou do TIDAL para localizar uma track já conhecida.
3. Manter `track_id` como identificador interno estável da tabela `tracks`.
4. Usar ISRC como apoio à reconciliação, sem o considerar suficiente por si só quando houver ambiguidades.
5. Não usar apenas o nome para identificar tracks, porque podem existir versões, remixes ou tracks homónimas.

### Unicidade de playlists

Rever a unicidade atual de `playlists.name`. Nomes não são uma identidade segura: duas playlists diferentes podem ter o mesmo nome. O plano deve priorizar `spotify_playlist_id` e `tidal_playlist_id`, mantendo o nome apenas como atributo apresentado ao utilizador.

Se existirem dados antigos baseados no nome, preparar uma migração que faça a associação aos IDs externos antes de remover ou alterar essa restrição.

### Estado de ficheiros

Para os relatórios, considerar como ficheiro local apenas uma linha em `files` cujo `missing_at IS NULL` e cujo ficheiro exista fisicamente no caminho esperado.

O formato deve ser normalizado para valores como `flac` e `mp3`, independentemente de diferenças entre maiúsculas e minúsculas na extensão.

## Fluxo proposto no sync

### 1. Obter e normalizar os dados

Depois de carregar a playlist do Spotify e concluir o matching com o TIDAL:

- Guardar o ID e o nome da playlist do Spotify.
- Para cada item do Spotify, guardar o ID Spotify, título, artistas, álbum, posição e, quando disponível, ISRC.
- Guardar o ID TIDAL correspondente quando o matching tiver sucesso.
- Preservar os itens sem correspondência no TIDAL como tracks da playlist, com estado de matching não resolvido.

O resultado da sincronização não deve ser representado apenas por uma lista de IDs TIDAL, porque essa lista perde as tracks que falharam no matching.

### 2. Fazer upsert da playlist

Adicionar uma operação de upsert na camada `MusicLibrary` que:

- Procure primeiro pelo ID Spotify.
- Atualize nome, ID TIDAL e `updated_at` quando a playlist já existir.
- Crie uma nova playlist quando não existir.
- Devolva sempre o `playlist_id` interno.

O upsert deve ser idempotente: repetir o sync da mesma playlist não deve criar duplicados.

### 3. Fazer upsert das tracks

Para cada track do resultado normalizado:

- Localizar a track pelo ID Spotify, ID TIDAL ou ISRC, por esta ordem de confiança.
- Criar a linha em `tracks` se não existir.
- Atualizar metadados e IDs externos sem substituir valores válidos por `NULL`.
- Reutilizar o `track_id` interno quando a track já existir.

Tracks sem matching no TIDAL também devem ser persistidas com os dados disponíveis do Spotify. Assim poderão aparecer no relatório de tracks sem ficheiro local e poderão ser reconciliadas num sync futuro.

### 4. Garantir as relações

Inserir uma linha em `playlist_tracks` para cada track da playlist usando `INSERT OR IGNORE` ou equivalente.

Esta operação deve ser executada tanto para tracks novas como para tracks já existentes. A chave primária `(playlist_id, track_id)` deve impedir duplicados, mas não deve impedir a reparação de uma relação em falta.

Definir explicitamente se a ordem da playlist é necessária. Se for necessária, adicionar uma coluna como `position` e tratar alterações de ordem no sync; se não for, manter a relação como associação de pertença.

### 5. Transação e consistência

O upsert da playlist, upsert das tracks e criação das relações devem ocorrer numa única transação da base de dados, por playlist.

Comportamento esperado em caso de erro:

- Se a transação falhar, não deixar uma playlist parcialmente persistida.
- Registar o erro com contexto suficiente para repetir a operação.
- Não remover relações ou tracks existentes automaticamente sem uma decisão explícita sobre o comportamento de remoção.

## Relatório por playlist

Criar uma operação de leitura na `MusicLibrary`, por exemplo `get_playlist_inventory(playlist_id)` ou equivalente, que devolva uma estrutura estável com:

```text
{
  playlist: { id, name, spotify_id, tidal_id },
  total_tracks: integer,
  tracks_with_flac: integer,
  tracks_with_mp3: integer,
  tracks_without_local_file: [
    { title, artists, spotify_id, tidal_id }
  ]
}
```

### Regras de contagem

- `total_tracks`: número de tracks distintas relacionadas com a playlist.
- `tracks_with_flac`: número de tracks distintas com pelo menos um FLAC local válido.
- `tracks_with_mp3`: número de tracks distintas com pelo menos um MP3 local válido.
- `tracks_without_local_file`: tracks relacionadas com a playlist sem FLAC nem MP3 local válido.
- Um mesmo ficheiro ou múltiplos ficheiros do mesmo formato contam apenas uma vez por track.
- Uma track com FLAC e MP3 conta nas duas contagens de formato.
- Ficheiros com `missing_at` preenchido não contam como locais.

As contagens devem ser feitas com `COUNT(DISTINCT track_id)` e agregações condicionais, evitando que múltiplas localizações ou cópias do mesmo ficheiro inflacionem os resultados.

### Critério de correspondência local

O relatório deve basear-se na associação `files.track_id`, não apenas no nome do ficheiro. O nome e os artistas devem ser devolvidos para permitir ação manual, mas não devem ser usados como única prova de correspondência.

## Nova feature: verificação técnica dos ficheiros MP3

### Objetivo

Adicionar uma verificação técnica aos ficheiros MP3 locais, independente da associação da track à playlist. A verificação deve confirmar se o ficheiro é legível, se contém um stream MP3 válido e se cumpre os requisitos de qualidade definidos para a biblioteca e para DJing.

O FFmpeg/ffprobe será a ferramenta principal, porque valida o conteúdo do stream e não depende apenas das extensões ou das tags ID3.

### 1. Descoberta dos ficheiros

Reutilizar as localizações registadas em `locations` e os caminhos da tabela `files`, em vez de depender de uma única pasta fixa. A verificação deve:

- Selecionar ficheiros com formato `mp3` e que não estejam marcados como ausentes.
- Permitir verificar um ficheiro, uma localização, uma playlist ou a biblioteca inteira.
- Ignorar ficheiros temporários como `._*`.
- Confirmar que o caminho ainda existe antes de iniciar o `ffprobe`.
- Guardar a data e o resultado da última verificação.

Para uma verificação completa, o equivalente operacional deverá percorrer todos os MP3 e executar `ffprobe` com saída estruturada. A implementação deve usar `subprocess` com argumentos separados, timeout e parsing de JSON (`-of json`), não parsing frágil de texto de terminal.

Exemplo de diagnóstico manual:

```bash
find "/path/to/music" -type f -iname "*.mp3" -print0 |
while IFS= read -r -d '' file; do
    ffprobe -v error \
        -show_entries format=duration \
        -show_entries stream=codec_name,codec_type,bit_rate,sample_rate,channels \
        -of default=noprint_wrappers=1 \
        "$file" >/dev/null || echo "ERROR: $file"
done
```

Na aplicação, substituir o loop shell por uma função Python que devolva um resultado por ficheiro, incluindo o erro técnico e os valores detetados.

### 2. Dados técnicos a recolher

Para cada MP3, recolher e persistir, quando disponíveis:

- `codec_name` e `codec_type`.
- Bitrate médio e bitrate por frame, para permitir distinguir CBR de VBR.
- Sample rate.
- Número de canais.
- Duração.
- Número de frames e eventuais erros de leitura/decoding.
- Estado das tags ID3.
- Presença de artwork, apenas como informação, não como critério de qualidade áudio.
- Data da verificação, versão do `ffprobe` e mensagem de erro.

Avaliar se estes campos pertencem diretamente a `files` ou a uma tabela própria, por exemplo `file_validation_results`. Uma tabela própria é preferível se for necessário manter histórico de verificações; campos em `files` são suficientes se apenas for necessário o último resultado.

### 3. Verificação de legibilidade e integridade

Executar duas verificações complementares:

1. `ffprobe` para validar o contentor, streams e metadados técnicos.
2. Um teste de decoding completo com FFmpeg, por exemplo para enviar o áudio para `null`, com `-v error` e `-xerror`, para detetar frames ilegíveis que uma leitura superficial possa não revelar.

Um ficheiro deve ser marcado como tecnicamente inválido quando:

- O processo falhar, exceder o timeout ou não produzir um stream de áudio.
- O codec não for `mp3`.
- Existirem erros de parsing ou decoding.
- A duração for inexistente, não finita ou menor ou igual a zero.

O resultado deve distinguir `probe_error`, `decode_error`, `invalid_stream`, `valid` e outros estados necessários, em vez de guardar apenas um booleano.

### 4. Regras de qualidade para DJing

Separar validade técnica de conformidade com o perfil de qualidade. Um MP3 pode ser reproduzível e tecnicamente válido sem cumprir o perfil escolhido.

Perfil inicial sugerido, configurável:

- Codec: `mp3`.
- Bitrate: 320 kbps CBR como alvo.
- Sample rate: 44.1 kHz.
- Canais: stereo, ou seja, 2 canais.
- Duração: superior a zero.
- Frames: sem erros de parsing ou decoding.
- VBR: detetado e reportado separadamente de CBR.
- Joint Stereo: aceite como válido, sem o marcar como defeito.
- Tags ID3: validadas separadamente; tags inválidas devem gerar aviso, não invalidar automaticamente o áudio.
- Artwork: opcional e nunca deve afetar a classificação da qualidade áudio.

Devolver pelo menos duas classificações:

- `technical_status`: se o ficheiro é legível e contém áudio MP3 válido.
- `quality_status`: se cumpre o perfil configurado.

Exemplos de motivos de não conformidade: `not_320kbps`, `vbr`, `unexpected_sample_rate`, `not_stereo`, `zero_duration`, `decode_error` ou `invalid_id3`.

### 5. Persistência na base de dados

Adicionar uma migration para guardar o último resultado por ficheiro ou um histórico, conforme a decisão da Fase 1. O modelo deve permitir:

- Consultar rapidamente MP3 tecnicamente válidos.
- Diferenciar ficheiros inválidos de ficheiros ainda não verificados.
- Repetir a análise depois de uma alteração do ficheiro.
- Invalidar ou repetir a análise quando `file_size`, caminho ou data de modificação mudarem.
- Guardar o erro sem perder os metadados válidos anteriormente recolhidos.

Usar uma transação para persistir o resultado de cada ficheiro. Não remover o registo do ficheiro nem a relação com a track quando a validação falhar.

### 6. Integração com o inventário da playlist

Definir se as contagens existentes devem considerar:

- Qualquer MP3 local.
- Apenas MP3 tecnicamente válidos.
- Apenas MP3 que também cumpram o perfil de qualidade.

Recomendação: manter contagens distintas no relatório, por exemplo `tracks_with_mp3`, `tracks_with_valid_mp3` e `tracks_with_quality_mp3`, para não esconder a diferença entre presença, legibilidade e conformidade.

Uma track com vários MP3 deve continuar a contar uma vez por categoria. Se houver um MP3 inválido e um MP3 válido da mesma track, a track conta como tendo MP3 válido, mas o relatório deve poder listar o ficheiro inválido separadamente.

### 7. Interface e execução

Adicionar uma operação explícita de verificação, sem a executar automaticamente em cada sync por defeito. A interface deve permitir:

- Verificar a biblioteca inteira.
- Verificar apenas os ficheiros desatualizados ou nunca verificados.
- Verificar os MP3 de uma playlist.
- Mostrar progresso, total de ficheiros, válidos, inválidos e não conformes.
- Consultar o caminho e o motivo de cada problema.

O processo deve limitar concorrência para não saturar CPU e disco, e deve continuar nos restantes ficheiros quando um ficheiro individual falhar.

### 8. Testes de aceitação da feature

- MP3 válido a 320 kbps CBR, 44.1 kHz e stereo é classificado como tecnicamente válido e conforme.
- MP3 VBR é detetado e separado de CBR.
- Joint Stereo não é marcado como erro.
- Ficheiro com extensão `.mp3`, mas codec diferente, é rejeitado como stream MP3.
- Ficheiro corrompido ou com frames ilegíveis é detetado pelo `ffprobe` ou pelo teste de decoding.
- Duração zero ou ausente é reportada como inválida.
- Sample rate diferente de 44.1 kHz e bitrate diferente de 320 kbps geram não conformidade, sem necessariamente indicar ficheiro ilegível.
- Tags ID3 inválidas geram o estado/motivo definido, sem confundir erro de tags com erro de áudio.
- Artwork ausente não afeta a validade nem a qualidade áudio.
- Uma falha num ficheiro não interrompe a verificação da biblioteca.
- Repetir a verificação sem alterações não cria resultados duplicados.
- Alterar o ficheiro força uma nova verificação.
- O inventário da playlist distingue presença de MP3, validade técnica e conformidade de qualidade.

## Migração e integridade

1. Inventariar a base de dados existente antes da alteração.
2. Criar uma migration versionada para quaisquer alterações de schema.
3. Adicionar índices para as consultas por `spotify_playlist_id`, `tidal_playlist_id` e para a combinação usada nas relações.
4. Avaliar constraints de unicidade para IDs externos nas tabelas `playlists` e `tracks`.
5. Executar uma rotina de reconciliação para detetar relações inválidas ou tracks duplicadas antes de ativar o novo fluxo.
6. Garantir que as foreign keys continuam ativas em todas as ligações.
7. Definir uma política para playlists e tracks removidas da origem: manter histórico, remover relações, ou marcar como inativas. Não apagar dados silenciosamente.

## Fases de execução

### Fase 1: Contrato e diagnóstico

- Confirmar se a playlist deve guardar ordem e duplicados de tracks.
- Confirmar quais diretórios e localizações contam como locais.
- Documentar exemplos de dados atuais e casos ambíguos de matching.
- Definir o contrato de retorno do relatório.

### Fase 2: Camada de persistência

- Implementar as operações transacionais de upsert.
- Implementar a garantia de relações playlist-track.
- Rever constraints, índices e migrations.
- Criar testes unitários para inserção, repetição e reparação de relações.

### Fase 3: Integração com o sync

- Construir um resultado normalizado que inclua matches com sucesso e falhas.
- Persistir os dados no final do sync, depois do matching e antes de terminar a operação.
- Garantir que o mesmo comportamento é usado no sync iniciado pela CLI e pelo fluxo de download.
- Testar falhas parciais e repetição do sync.

### Fase 4: Inventário local

- Implementar a consulta de contagens por playlist.
- Implementar a consulta/lista de tracks sem ficheiro local.
- Validar o relatório depois de importar, converter, mover e remover ficheiros.
- Decidir se o relatório será exposto primeiro pela CLI, por API, ou por ambos.

### Fase 5: Reconciliação e manutenção

- Executar a reconciliação dos diretórios antes de gerar relatórios.
- Monitorizar inconsistências entre ficheiros, tracks e relações.
- Adicionar logs e métricas para tracks sem matching e tracks sem ficheiro.
- Atualizar a documentação e o README quando a funcionalidade estiver implementada.

## Testes de aceitação

- Sincronizar uma playlist nova e verificar uma linha em `playlists`.
- Verificar uma linha em `tracks` para cada item Spotify, incluindo itens sem matching TIDAL.
- Repetir o sync e confirmar que não existem playlists, tracks ou relações duplicadas.
- Remover manualmente uma relação e repetir o sync; confirmar que a relação é recriada.
- Associar FLAC e MP3 à mesma track; confirmar que ambas as contagens aumentam uma unidade.
- Associar várias cópias da mesma track; confirmar que as contagens usam tracks distintas.
- Remover um ficheiro e reconciliar a localização; confirmar que deixa de contar.
- Confirmar que a lista de tracks sem ficheiro contém o título e os artistas corretos.
- Confirmar que uma playlist vazia tem contagens a zero e comportamento definido.
- Confirmar que duas playlists com o mesmo nome, mas IDs diferentes, não partilham a mesma entidade.

## Resultado esperado

Após a implementação deste plano, a base de dados será a fonte de verdade para a relação entre playlists, tracks e ficheiros locais. O sync passará a guardar também informação incompleta, em vez de perder tracks sem matching, e será possível responder de forma determinística:

- Quantas tracks tem cada playlist.
- Quantas dessas tracks têm FLAC.
- Quantas têm MP3.
- Quais não têm qualquer ficheiro local.
