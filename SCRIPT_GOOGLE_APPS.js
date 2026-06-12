function acordarBotReceitas() {
  // Substitua 'robsonvit' e 'bot-receitas-facebook' pelo seu usuário e repositório
  var url = "https://api.github.com/repos/robsonvit/bot-receitas-facebook/actions/workflows/main.yml/dispatches";
  
  // Seu Personal Access Token (PAT) do GitHub com permissão de 'repo'
  // IMPORTANTE: Nunca compartilhe esse token publicamente!
  var token = "SEU_GITHUB_PERSONAL_ACCESS_TOKEN_AQUI"; 
  
  var options = {
    "method": "post",
    "headers": {
      "Authorization": "Bearer " + token,
      "Accept": "application/vnd.github.v3+json"
    },
    // Aqui garantimos que ele rode na branch principal (main)
    "payload": JSON.stringify({"ref": "main"}) 
  };
  
  try {
    var response = UrlFetchApp.fetch(url, options);
    var statusCode = response.getResponseCode();
    
    if (statusCode == 204) {
      Logger.log("✅ Sucesso! O sinal foi enviado para o GitHub e o Bot está trabalhando.");
    } else {
      Logger.log("❌ Atenção, erro. Código: " + statusCode);
      Logger.log("Detalhes: " + response.getContentText());
    }
  } catch(e) {
    Logger.log("❌ Erro de conexão: " + e.toString());
  }
}
